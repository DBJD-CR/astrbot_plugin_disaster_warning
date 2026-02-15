const { Snackbar, Alert, IconButton } = MaterialUI;
const { useState, useEffect, createContext, useContext } = React;

/**
 * Toast 通知组件
 * 用于替代原生 alert()，提供更美观的提示信息
 */

// Toast Context
const ToastContext = createContext();

// Toast Provider
function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    const showToast = (message, severity = 'info', duration = 4000) => {
        const id = Date.now() + Math.random();
        const newToast = {
            id,
            message,
            severity, // 'success', 'error', 'warning', 'info'
            duration,
            open: true,
            autoCloseTimer: null,
            removeTimer: null
        };
        
        setToasts(prev => [...prev, newToast]);

        // 自动关闭
        if (duration > 0) {
            const timerId = setTimeout(() => {
                closeToast(id);
            }, duration);
            
            // 存储定时器 ID
            setToasts(prev => prev.map(t => 
                t.id === id ? { ...t, autoCloseTimer: timerId } : t
            ));
        }
    };

    const closeToast = (id) => {
        setToasts(prev => prev.map(t => {
            if (t.id === id) {
                // 清除自动关闭定时器
                if (t.autoCloseTimer) {
                    clearTimeout(t.autoCloseTimer);
                }
                return { ...t, open: false, autoCloseTimer: null };
            }
            return t;
        }));
        
        // 延迟移除（等待动画完成）
        const removeTimerId = setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 200);
        
        // 存储移除定时器 ID
        setToasts(prev => prev.map(t => 
            t.id === id ? { ...t, removeTimer: removeTimerId } : t
        ));
    };
    
    // 组件卸载时清理所有定时器
    useEffect(() => {
        return () => {
            toasts.forEach(toast => {
                if (toast.autoCloseTimer) {
                    clearTimeout(toast.autoCloseTimer);
                }
                if (toast.removeTimer) {
                    clearTimeout(toast.removeTimer);
                }
            });
        };
    }, [toasts]);

    return (
        <ToastContext.Provider value={{ showToast }}>
            {children}
            <div style={{
                position: 'fixed',
                top: '20px',
                right: '20px',
                zIndex: 9999,
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                maxWidth: '400px'
            }}>
                {toasts.map(toast => (
                    <Snackbar
                        key={toast.id}
                        open={toast.open}
                        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
                        sx={{
                            position: 'relative',
                            left: 'auto',
                            right: 'auto',
                            top: 'auto',
                            bottom: 'auto',
                            transform: 'none'
                        }}
                    >
                        <Alert
                            severity={toast.severity}
                            onClose={() => closeToast(toast.id)}
                            variant="filled"
                            sx={{
                                width: '100%',
                                borderRadius: '12px',
                                boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
                                fontSize: '14px',
                                fontWeight: 500,
                                '& .MuiAlert-icon': {
                                    fontSize: '22px'
                                }
                            }}
                        >
                            {toast.message}
                        </Alert>
                    </Snackbar>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

// Custom hook
function useToast() {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within ToastProvider');
    }
    return context;
}

// 暴露给全局
window.ToastProvider = ToastProvider;
window.useToast = useToast;
