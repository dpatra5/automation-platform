import React from 'react';
import { FolderOpen } from 'lucide-react';

interface Props {
  title: string;
  description: string;
  icon?: React.ElementType;
  action?: React.ReactNode;
}

export const EmptyState = ({ title, description, icon: Icon = FolderOpen, action }: Props) => {
  return (
    <div className="card flex flex-col items-center justify-center p-12 text-center">
      <div className="w-14 h-14 mb-4 rounded-2xl bg-primary-50 flex items-center justify-center">
        <Icon className="w-7 h-7 text-primary-500" />
      </div>
      <h3 className="text-base font-semibold text-ink mb-1.5">{title}</h3>
      <p className="text-sm text-ink-muted max-w-sm mb-5">{description}</p>
      {action}
    </div>
  );
};
