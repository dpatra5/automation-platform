import React from 'react';

export const SkeletonLoader = ({ className = '', count = 1 }: { className?: string, count?: number }) => {
  return (
    <div className="flex flex-col gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`animate-pulse bg-line/70 rounded-2xl ${className}`}
        />
      ))}
    </div>
  );
};
