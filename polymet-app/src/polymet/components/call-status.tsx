import React from "react";
import { cn } from "@/lib/utils";
import { PhoneIcon, PhoneOffIcon, CheckIcon, XIcon } from "lucide-react";
import { Loader2 } from "lucide-react";

export type CallStatus =
  | "idle"
  | "connecting"
  | "in-progress"
  | "completed"
  | "failed";

interface CallStatusProps {
  status: CallStatus;
  duration?: string;
  className?: string;
}

export function CallStatus({ status, duration, className }: CallStatusProps) {
  const getStatusIcon = () => {
    switch (status) {
      case "connecting":
        return (
          <div className="animate-pulse flex items-center">
            <PhoneIcon className="h-5 w-5 text-amber-500 mr-2" />
            <span>Connecting...</span>
          </div>
        );

      case "in-progress":
        return (
          <div className="flex items-center">
            <div className="relative mr-2">
              <PhoneIcon className="h-5 w-5 text-green-500" />
              <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-green-500 animate-ping" />
            </div>
            <span>Call in progress</span>
            {duration && (
              <span className="ml-2 text-muted-foreground">{duration}</span>
            )}
          </div>
        );

      case "completed":
        return (
          <div className="flex items-center">
            <CheckIcon className="h-5 w-5 text-green-500 mr-2" />
            <span>Call completed</span>
            {duration && (
              <span className="ml-2 text-muted-foreground">{duration}</span>
            )}
          </div>
        );

      case "failed":
        return (
          <div className="flex items-center">
            <PhoneOffIcon className="h-5 w-5 text-destructive mr-2" />
            <span>Call failed</span>
          </div>
        );

      default:
        return (
          <div className="flex items-center">
            <PhoneIcon className="h-5 w-5 text-muted-foreground mr-2" />
            <span>Ready to call</span>
          </div>
        );
    }
  };

  const getStatusClass = () => {
    switch (status) {
      case "connecting":
        return "bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-400";
      case "in-progress":
        return "bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400";
      case "completed":
        return "bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400";
      case "failed":
        return "bg-destructive/10 border-destructive/20 text-destructive";
      default:
        return "bg-muted border-muted-foreground/20";
    }
  };

  return (
    <div
      className={cn(
        "flex items-center justify-center px-4 py-2 rounded-md border",
        getStatusClass(),
        className
      )}
    >
      {getStatusIcon()}
    </div>
  );
}

export default CallStatus;
