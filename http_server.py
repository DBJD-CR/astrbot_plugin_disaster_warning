"""
灾害预警插件 HTTP 服务器
提供独立的网页配置界面
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any

import aiohttp
from aiohttp import web
from astrbot.api import logger as astrbot_logger

# 配置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('disaster_warning_http_server')


class DisasterWarningHTTPServer:
    """灾害预警插件 HTTP 服务器"""
    
    def __init__(self, config: Dict[str, Any], config_save_callback=None, disaster_service=None):
        self.config = config
        self.config_save_callback = config_save_callback
        self.disaster_service = disaster_service  # 添加灾害服务实例
        self.app = web.Application(middlewares=[self.error_middleware])
        self.runner = None
        self.port = config.get('http_config', {}).get('port', 8080)
        self.host = config.get('http_config', {}).get('host', '127.0.0.1')
        self.enabled = config.get('http_config', {}).get('enabled', False)
        self.auth_token = config.get('http_config', {}).get('auth_token', '')
        self.setup_routes()
    
    @web.middleware
    async def error_middleware(self, request, handler):
        """错误处理中间件"""
        try:
            response = await handler(request)
            return response
        except Exception as e:
            log.error(f"请求处理错误: {e}")
            return web.json_response({
                "status": "error", 
                "message": f"服务器内部错误: {str(e)}"
            }, status=500)
    
    def setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/', self.index_handler)
        self.app.router.add_get('/config', self.get_config_handler)
        self.app.router.add_post('/config', self.update_config_handler)
        self.app.router.add_get('/static/{path:.*}', self.static_handler)
        self.app.router.add_get('/api/status', self.status_handler)
        self.app.router.add_get('/api/service_status', self.service_status_handler)
        self.app.router.add_get('/api/data_sources', self.get_data_sources_handler)
        # 添加资源文件路由
        self.app.router.add_static('/resources/', path=os.path.join(os.path.dirname(__file__), 'resources'), name='static')
    
    async def index_handler(self, request):
        """主页处理器"""
        try:
            with open(os.path.join(os.path.dirname(__file__), 'resources', 'config.html'), 'r', encoding='utf-8') as f:
                html_content = f.read()
            return web.Response(text=html_content, content_type='text/html')
        except FileNotFoundError:
            log.error("配置页面文件不存在")
            return web.Response(text="配置页面文件不存在", status=500)
        except Exception as e:
            log.error(f"加载主页失败: {e}")
            return web.Response(text=f"加载页面失败: {e}", status=500)
    
    async def static_handler(self, request):
        """处理静态文件请求"""
        path = request.match_info['path']
        file_path = os.path.join(os.path.dirname(__file__), 'resources', path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return web.FileResponse(file_path)
        else:
            return web.Response(status=404, text="File not found")
    
    async def get_config_handler(self, request):
        """获取配置处理器 - 只返回安全的配置，不包含敏感信息"""
        try:
            # 过滤掉敏感配置项
            safe_config = self._get_safe_config(self.config)
            return web.json_response(safe_config)
        except Exception as e:
            log.error(f"获取配置失败: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    def _get_safe_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """获取安全的配置副本（移除敏感信息）"""
        import copy
        safe_config = copy.deepcopy(config)
        # 移除认证令牌等敏感信息
        if 'http_config' in safe_config and 'auth_token' in safe_config['http_config']:
            safe_config['http_config']['auth_token'] = ''  # 不返回认证令牌
        return safe_config
    
    async def get_data_sources_handler(self, request):
        """获取数据源列表"""
        try:
            # 从模型文件导入数据源配置
            from .models.data_source_config import DATA_SOURCE_CONFIGS
            
            # 转换为适合前端显示的格式
            data_sources = {}
            for source_id, config in DATA_SOURCE_CONFIGS.items():
                data_sources[source_id] = {
                    "source_id": config.source_id,
                    "source_type": config.source_type.value,
                    "display_name": config.display_name,
                    "description": config.description,
                    "supports_report_count": config.supports_report_count,
                    "supports_final_report": config.supports_final_report,
                    "uses_intensity": config.uses_intensity,
                    "uses_scale": config.uses_scale,
                    "priority": config.priority
                }
            
            return web.json_response({
                "status": "success",
                "data_sources": data_sources
            })
        except Exception as e:
            log.error(f"获取数据源列表失败: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
        """更新配置处理器"""
        try:
            # 验证认证令牌（如果配置了）
            if self.auth_token:
                auth_header = request.headers.get('Authorization')
                if not auth_header or not auth_header.startswith('Bearer ') or auth_header[7:] != self.auth_token:
                    # 也可以检查请求体中的令牌
                    request_data = await request.json()
                    token_in_body = request_data.get('auth_token')
                    if token_in_body != self.auth_token:
                        return web.json_response({"status": "error", "message": "认证失败"}, status=401)
            
            new_config = await request.json()
            log.debug(f"收到新的配置: {new_config}")
            
            # 保留原始配置中的敏感信息（如认证令牌）
            if 'http_config' in self.config and 'auth_token' in self.config['http_config']:
                # 保存原始认证令牌
                original_token = self.config['http_config']['auth_token']
                if 'http_config' not in new_config:
                    new_config['http_config'] = {}
                # 如果新配置中没有提供新令牌，则保留原令牌
                if 'auth_token' not in new_config['http_config'] or not new_config['http_config']['auth_token']:
                    new_config['http_config']['auth_token'] = original_token
            
            # 更新内存中的配置
            self._deep_update_config(self.config, new_config)
            log.debug(f"更新后的配置: {self.config}")
            
            # 如果提供了保存回调，调用它
            if self.config_save_callback:
                try:
                    # 异步调用配置保存
                    if asyncio.iscoroutinefunction(self.config_save_callback):
                        await self.config_save_callback(self.config)
                    else:
                        # 如果不是异步函数，使用线程池执行
                        await asyncio.get_event_loop().run_in_executor(None, self.config_save_callback, self.config)
                except Exception as e:
                    log.error(f"调用配置保存回调失败: {e}")
                    return web.json_response({"status": "error", "message": f"保存配置失败: {e}"}, status=500)
            
            log.info("配置已更新并保存")
            return web.json_response({"status": "success", "message": "配置已保存"})
        except json.JSONDecodeError:
            log.error("配置更新失败: 无效的JSON格式")
            return web.json_response({"status": "error", "message": "无效的JSON格式"}, status=400)
        except Exception as e:
            log.error(f"更新配置失败: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    def _deep_update_config(self, config: Dict[str, Any], updates: Dict[str, Any]):
        """深度更新配置字典"""
        for key, value in updates.items():
            if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                self._deep_update_config(config[key], value)
            else:
                config[key] = value
    
    async def status_handler(self, request):
        """服务器状态处理器"""
        # 获取插件的运行状态信息
        service_status = {}
        if hasattr(self, 'disaster_service'):
            try:
                service_status = self.disaster_service.get_service_status()
            except:
                service_status = {}
        
        return web.json_response({
            "status": "running",
            "port": self.port,
            "host": self.host,
            "enabled": self.enabled,
            "auth_required": bool(self.auth_token),
            "plugin_service_status": service_status
        })
    
    async def service_status_handler(self, request):
        """获取插件服务状态"""
        try:
            # 需要从配置中获取灾害服务实例
            if hasattr(self, 'disaster_service') and self.disaster_service:
                status = self.disaster_service.get_service_status()
                return web.json_response({
                    "status": "success",
                    "data": status
                })
            else:
                # 如果没有获取到服务实例，返回基本状态
                return web.json_response({
                    "status": "success",
                    "data": {
                        "running": False,
                        "message": "服务实例未初始化或不可用"
                    }
                })
        except Exception as e:
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
    
    async def get_data_sources_handler(self, request):
        """获取数据源列表处理器"""
        try:
            from .models.data_source_config import DATA_SOURCE_CONFIGS
            data_sources = {}
            for source_id, config in DATA_SOURCE_CONFIGS.items():
                data_sources[source_id] = {
                    "display_name": config.display_name,
                    "description": config.description,
                    "type": config.source_type.value,
                    "supports_report_count": config.supports_report_count,
                    "supports_final_report": config.supports_final_report,
                    "uses_intensity": config.uses_intensity,
                    "uses_scale": config.uses_scale,
                    "priority": config.priority
                }
            
            return web.json_response({
                "status": "success",
                "data_sources": data_sources
            })
        except Exception as e:
            log.error(f"获取数据源列表失败: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    async def test_connection_handler(self, request):
        """测试连接处理器"""
        try:
            # 这里可以添加实际的连接测试逻辑
            return web.json_response({
                "status": "success",
                "message": "服务器连接正常",
                "timestamp": str(request.time())
            })
        except Exception as e:
            log.error(f"测试连接失败: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    async def start(self):
        """启动HTTP服务器"""
        if not self.enabled:
            log.info("HTTP服务器未启用，跳过启动")
            return
            
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            site = web.TCPSite(self.runner, self.host, self.port)
            await site.start()
            log.info(f"HTTP服务器已启动，地址: {self.host}:{self.port}")
            log.info(f"访问地址: http://{self.host}:{self.port}")
        except Exception as e:
            log.error(f"启动HTTP服务器失败: {e}")
            raise
    
    async def stop(self):
        """停止HTTP服务器"""
        if self.runner:
            await self.runner.cleanup()
            log.info("HTTP服务器已停止")