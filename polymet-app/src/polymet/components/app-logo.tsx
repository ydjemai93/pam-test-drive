import React from "react";

export function AppLogo({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center ${className}`}>
      <svg
        width="32"
        height="32"
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="h-6 w-6"
      >
        <path
          d="M50 10C67.9086 10 82.5 24.5914 82.5 42.5C82.5 60.4086 67.9086 75 50 75V90C30 75 17.5 60.4086 17.5 42.5C17.5 24.5914 32.0914 10 50 10Z"
          fill="url(#paint0_linear)"
          stroke="url(#paint1_linear)"
          strokeWidth="5"
        />

        <defs>
          <linearGradient
            id="paint0_linear"
            x1="50"
            y1="10"
            x2="50"
            y2="90"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#2E8B57" />

            <stop offset="1" stopColor="#7FFF00" />
          </linearGradient>
          <linearGradient
            id="paint1_linear"
            x1="50"
            y1="10"
            x2="50"
            y2="90"
            gradientUnits="userSpaceOnUse"
          >
            <stop stopColor="#2E8B57" />

            <stop offset="1" stopColor="#7FFF00" />
          </linearGradient>
        </defs>
      </svg>
      <span className="ml-2 text-lg font-semibold">PAM</span>
    </div>
  );
}
