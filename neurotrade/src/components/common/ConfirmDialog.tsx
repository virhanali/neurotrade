import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '@/utils/helpers';

interface ConfirmDialogProps {
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    cancelText?: string;
    variant?: 'danger' | 'warning' | 'info';
    isLoading?: boolean;
    onConfirm: () => void;
    onCancel: () => void;
}

export function ConfirmDialog({
    isOpen,
    title,
    message,
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    variant = 'danger',
    isLoading = false,
    onConfirm,
    onCancel
}: ConfirmDialogProps) {
    if (!isOpen) return null;

    const variantStyles = {
        danger: {
            icon: 'text-rose-600 dark:text-rose-400 bg-rose-100 dark:bg-rose-900/20',
            button: 'bg-rose-500 hover:bg-rose-600 text-white',
        },
        warning: {
            icon: 'text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/20',
            button: 'bg-amber-500 hover:bg-amber-600 text-white',
        },
        info: {
            icon: 'text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/20',
            button: 'bg-blue-500 hover:bg-blue-600 text-white',
        }
    };

    const styles = variantStyles[variant];

    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
                onClick={!isLoading ? onCancel : undefined}
            />

            {/* Dialog */}
            <div className="relative w-full max-w-md bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 animate-scale-up">
                <button
                    onClick={onCancel}
                    disabled={isLoading}
                    className="absolute top-4 right-4 text-slate-400 hover:text-slate-500 dark:hover:text-slate-300 disabled:opacity-50"
                >
                    <X className="w-5 h-5" />
                </button>

                <div className="flex gap-4">
                    <div className={cn("flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center", styles.icon)}>
                        <AlertTriangle className="w-6 h-6" />
                    </div>

                    <div className="flex-1">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                            {title}
                        </h3>
                        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                            {message}
                        </p>

                        <div className="mt-6 flex justify-end gap-3">
                            <button
                                onClick={onCancel}
                                disabled={isLoading}
                                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                            >
                                {cancelText}
                            </button>
                            <button
                                onClick={onConfirm}
                                disabled={isLoading}
                                className={cn(
                                    "px-4 py-2 text-sm font-bold rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50",
                                    styles.button
                                )}
                            >
                                {isLoading && <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
                                {confirmText}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
}
