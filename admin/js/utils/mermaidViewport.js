(() => {
    /**
     * 为 Markdown 视图内部生成的 SVG 图表（Mermaid 模块）提供高阶视口控制算法。
     * 
     * 主要交互包括：
     * 1. 自适应适配：去除 SVG 的固定宽高限制，计算画布与当前外层 viewport 视口的比例，完成初次挂载时的完美自适应缩放（Fit Scale）。
     * 2. 无极缩放 (Zooming)：支持点击加减按钮、或者按住 Ctrl/Meta 键并滑动滚轮进行以鼠标当前悬停处为锚点的数学视口平滑缩放。
     * 3. 手势平移拖拽 (Panning)：检测到鼠标/触摸点击并移动时，通过改变 scrollTop 与 scrollLeft 实现丝滑拖拽。
     * 4. 边界裁剪限制：限制缩放比例在 [0.35, 12] 倍之间，防范因过大或过小引起的白屏。
     */
    function attachMermaidViewportControls(block, cleanupFns) {
        const svg = block.querySelector('svg');
        if (!svg) return;

        const currentSvg = svg;
        const svgViewBox = currentSvg.viewBox?.baseVal;
        
        // 提取固有图表高度和宽度，未检测到则给出默认兜底
        const fallbackWidth = Number(currentSvg.getAttribute('width')) || currentSvg.clientWidth || 1200;
        const fallbackHeight = Number(currentSvg.getAttribute('height')) || currentSvg.clientHeight || 800;
        const intrinsicWidth = svgViewBox && svgViewBox.width ? svgViewBox.width : fallbackWidth;
        const intrinsicHeight = svgViewBox && svgViewBox.height ? svgViewBox.height : fallbackHeight;

        // 剥离硬宽高限制，将样式控制权让给 JS 视口驱动层
        currentSvg.removeAttribute('width');
        currentSvg.removeAttribute('height');
        currentSvg.style.width = `${intrinsicWidth}px`;
        currentSvg.style.height = `${intrinsicHeight}px`;
        currentSvg.style.maxWidth = 'none';
        currentSvg.style.maxHeight = 'none';

        // 擦除先前的遗留节点与工具条，防止在重排时产生堆积
        const existingViewport = block.querySelector('.notification-md-mermaid-viewport');
        if (existingViewport) existingViewport.remove();
        const existingToolbar = block.parentElement?.querySelector('.notification-md-mermaid-toolbar');
        if (existingToolbar) existingToolbar.remove();

        // 构造独立的滚动平移视口层与渲染画布层
        const viewport = document.createElement('div');
        viewport.className = 'notification-md-mermaid-viewport';
        const canvas = document.createElement('div');
        canvas.className = 'notification-md-mermaid-canvas';
        canvas.style.width = `${intrinsicWidth}px`;
        canvas.style.height = `${intrinsicHeight}px`;
        
        canvas.appendChild(currentSvg);
        viewport.appendChild(canvas);
        block.appendChild(viewport);

        // 构造缩放重置控制工具栏
        const toolbar = document.createElement('div');
        toolbar.className = 'notification-md-mermaid-toolbar';
        toolbar.innerHTML = [
            '<button type="button" class="notification-md-mermaid-tool-btn" data-action="zoom-in">＋</button>',
            '<button type="button" class="notification-md-mermaid-tool-btn" data-action="zoom-out">－</button>',
            '<button type="button" class="notification-md-mermaid-tool-btn" data-action="reset">重置</button>',
        ].join('');
        block.parentElement.insertBefore(toolbar, block);

        // 初始化可变的物理视口参数
        const stateRef = { scale: 1, dragging: false, pointerId: null, startX: 0, startY: 0, startScrollLeft: 0, startScrollTop: 0 };
        // 限制缩放档位区间
        const clampScale = (value) => Math.min(12, Math.max(0.35, value));
        
        // 计算使图表刚好全部可见的最佳初次挂载缩放比
        const getFitScale = () => {
            const viewportWidth = viewport.clientWidth || intrinsicWidth;
            const viewportHeight = viewport.clientHeight || intrinsicHeight;
            if (!viewportWidth || !viewportHeight || !intrinsicWidth || !intrinsicHeight) return 1;
            return clampScale(Number(Math.min(viewportWidth / intrinsicWidth, viewportHeight / intrinsicHeight, 1).toFixed(3)));
        };

        // 执行缩放重绘渲染
        const applyScale = () => {
            canvas.style.width = `${intrinsicWidth * stateRef.scale}px`;
            canvas.style.height = `${intrinsicHeight * stateRef.scale}px`;
            currentSvg.style.width = '100%';
            currentSvg.style.height = '100%';
            
            // 下一帧判定是否需要显示鼠标拖拽抓取样式类
            requestAnimationFrame(() => {
                const canPanX = viewport.scrollWidth - viewport.clientWidth > 2;
                const canPanY = viewport.scrollHeight - viewport.clientHeight > 2;
                viewport.classList.toggle('is-pannable', canPanX || canPanY);
            });
        };

        // 将图表移动居中
        const centerViewport = () => {
            viewport.scrollLeft = Math.max((viewport.scrollWidth - viewport.clientWidth) / 2, 0);
            viewport.scrollTop = Math.max((viewport.scrollHeight - viewport.clientHeight) / 2, 0);
        };

        // 重置至初始自适应完美比例
        const resetTransform = () => {
            stateRef.scale = getFitScale();
            applyScale();
            requestAnimationFrame(centerViewport);
        };

        // 依据相对增量进行视口锚点精确缩放算法
        const zoomBy = (delta, originX = null, originY = null) => {
            const prevScale = stateRef.scale;
            const nextScale = clampScale(Number((prevScale + delta).toFixed(3)));
            if (nextScale === prevScale) return;
            
            const viewportRect = viewport.getBoundingClientRect();
            // 若未指定缩放中心点，默认以视口正中央作为缩放轴心
            const anchorClientX = originX === null ? viewportRect.left + viewportRect.width / 2 : originX;
            const anchorClientY = originY === null ? viewportRect.top + viewportRect.height / 2 : originY;
            const localX = anchorClientX - viewportRect.left;
            const localY = anchorClientY - viewportRect.top;
            
            // 演算缩放后需要滚动条位移的具体 scrollTop / scrollLeft，以保证视窗内焦点不动
            const contentX = (viewport.scrollLeft + localX) / prevScale;
            const contentY = (viewport.scrollTop + localY) / prevScale;
            stateRef.scale = nextScale;
            applyScale();
            viewport.scrollLeft = Math.max(0, contentX * nextScale - localX);
            viewport.scrollTop = Math.max(0, contentY * nextScale - localY);
            
            if (stateRef.scale <= 1.001) centerViewport();
        };

        // 响应工具条交互
        const onToolbarClick = (event) => {
            const action = event.target?.getAttribute('data-action');
            if (action === 'zoom-in') zoomBy(0.35);
            if (action === 'zoom-out') zoomBy(-0.35);
            if (action === 'reset') resetTransform();
        };

        // 响应 Ctrl + 滚轮的缩放操作
        const onWheel = (event) => {
            if (!(event.ctrlKey || event.metaKey)) return;
            event.preventDefault();
            zoomBy(event.deltaY < 0 ? 0.28 : -0.28, event.clientX, event.clientY);
        };

        // 响应拖动按下
        const onPointerDown = (event) => {
            const canPanX = viewport.scrollWidth - viewport.clientWidth > 2;
            const canPanY = viewport.scrollHeight - viewport.clientHeight > 2;
            if (!canPanX && !canPanY) return;
            
            stateRef.dragging = true;
            stateRef.pointerId = event.pointerId;
            stateRef.startX = event.clientX;
            stateRef.startY = event.clientY;
            stateRef.startScrollLeft = viewport.scrollLeft;
            stateRef.startScrollTop = viewport.scrollTop;
            viewport.classList.add('is-dragging');
            
            if (typeof viewport.setPointerCapture === 'function') {
                viewport.setPointerCapture(event.pointerId);
            }
        };

        // 响应手势移动
        const onPointerMove = (event) => {
            if (!stateRef.dragging || stateRef.pointerId !== event.pointerId) return;
            viewport.scrollLeft = stateRef.startScrollLeft - (event.clientX - stateRef.startX);
            viewport.scrollTop = stateRef.startScrollTop - (event.clientY - stateRef.startY);
        };

        // 响应拖拽松开
        const endDrag = (event) => {
            if (event && stateRef.pointerId !== event.pointerId) return;
            stateRef.dragging = false;
            viewport.classList.remove('is-dragging');
            if (event && typeof viewport.releasePointerCapture === 'function') {
                try { viewport.releasePointerCapture(event.pointerId); } catch (e) {}
            }
            stateRef.pointerId = null;
        };

        // 挂载各种物理指针事件
        toolbar.addEventListener('click', onToolbarClick);
        viewport.addEventListener('wheel', onWheel, { passive: false });
        viewport.addEventListener('pointerdown', onPointerDown);
        viewport.addEventListener('pointermove', onPointerMove);
        viewport.addEventListener('pointerup', endDrag);
        viewport.addEventListener('pointercancel', endDrag);
        
        // 收集注销句柄，以便卸载文档时防范内存残留
        cleanupFns.push(() => {
            toolbar.removeEventListener('click', onToolbarClick);
            viewport.removeEventListener('wheel', onWheel);
            viewport.removeEventListener('pointerdown', onPointerDown);
            viewport.removeEventListener('pointermove', onPointerMove);
            viewport.removeEventListener('pointerup', endDrag);
            viewport.removeEventListener('pointercancel', endDrag);
        });

        // 触发首帧渲染定位
        stateRef.scale = getFitScale();
        applyScale();
        requestAnimationFrame(centerViewport);
    }

    window.MermaidViewport = { attachMermaidViewportControls };
})();
