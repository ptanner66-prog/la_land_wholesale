/**
 * LA Land Wholesale Logo
 * 
 * White location pin with a sharper, thicker arrow passing through its circular center,
 * positioned above a horizontal rectangular base, on a solid black background.
 */
import { cn } from '@/lib/utils';

interface LogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const sizes = {
  sm: 'w-8 h-8',
  md: 'w-10 h-10',
  lg: 'w-12 h-12',
};

export function Logo({ className, size = 'md' }: LogoProps) {
  return (
    <div className={cn('rounded-lg bg-black p-1', sizes[size], className)}>
      <svg
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full"
      >
        {/* Location Pin */}
        <path
          d="M50 5C32.3 5 18 19.3 18 37C18 54.7 50 85 50 85C50 85 82 54.7 82 37C82 19.3 67.7 5 50 5ZM50 49C42.8 49 37 43.2 37 36C37 28.8 42.8 23 50 23C57.2 23 63 28.8 63 36C63 43.2 57.2 49 50 49Z"
          fill="white"
        />
        
        {/* Arrow passing through */}
        <path
          d="M30 45L70 25L65 40L85 35L45 55L50 42L30 45Z"
          fill="white"
          stroke="black"
          strokeWidth="2"
        />
        
        {/* Base rectangle */}
        <rect
          x="20"
          y="88"
          width="60"
          height="6"
          rx="2"
          fill="white"
        />
      </svg>
    </div>
  );
}

export function LogoWithText({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Logo size="md" />
      <div className="flex flex-col">
        <span className="font-bold text-lg leading-tight">LA Land</span>
        <span className="text-xs text-muted-foreground leading-tight">Wholesale</span>
      </div>
    </div>
  );
}

export default Logo;

