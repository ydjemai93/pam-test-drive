import React from "react";
import { Link, useLocation } from "react-router-dom";
import {
  HomeIcon,
  PhoneIcon,
  SettingsIcon,
  HelpCircleIcon,
  FileTextIcon,
  ZapIcon,
  PlayIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { AppLogo } from "@/polymet/components/app-logo";

export function SidebarWithRouter() {
  const location = useLocation();
  const currentPath = location.pathname;

  const navItems = [
    {
      name: "Dashboard",
      href: "/dashboard",
      icon: HomeIcon,
    },
    {
      name: "AI Agents",
      href: "/agents",
      icon: ZapIcon,
    },
    {
      name: "Call History",
      href: "/calls",
      icon: PhoneIcon,
    },
    {
      name: "Playground",
      href: "/playground",
      icon: PlayIcon,
    },
  ];

  const secondaryNavItems = [
    {
      name: "Settings",
      href: "/settings",
      icon: SettingsIcon,
    },
    {
      name: "Help Center",
      href: "/help",
      icon: HelpCircleIcon,
    },
    {
      name: "Documentation",
      href: "/docs",
      icon: FileTextIcon,
    },
  ];

  // Define the gradient color for icons
  const iconGradientClass = "text-[#2E8B57]";

  return (
    <div className="flex h-full flex-col border-r bg-background">
      <div className="flex h-14 items-center border-b px-4">
        <Link to="/dashboard" className="flex items-center gap-2 font-semibold">
          <AppLogo />
        </Link>
      </div>
      <div className="flex flex-1 flex-col overflow-auto py-2 font-thin">
        <nav className="grid gap-1 px-2 group-[.active]:bg-accent">
          {navItems.map((item) => (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground",
                currentPath === item.href
                  ? "bg-accent text-accent-foreground"
                  : "transparent"
              )}
            >
              <item.icon
                className={`h-4 w-4 ${currentPath === item.href ? "" : iconGradientClass}`}
              />

              {item.name}
            </Link>
          ))}
        </nav>
        <div className="flex-1"></div>
      </div>
      <nav className="grid gap-1 px-2 mb-4">
        {secondaryNavItems.map((item) => (
          <Link
            key={item.name}
            to={item.href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground",
              currentPath === item.href
                ? "bg-accent text-accent-foreground"
                : "transparent"
            )}
          >
            <item.icon
              className={`h-4 w-4 ${currentPath === item.href ? "" : iconGradientClass}`}
            />

            {item.name}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t">
        <div className="rounded-lg bg-muted p-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Pro Plan</p>
              <p className="text-xs text-muted-foreground">7 days remaining</p>
            </div>
          </div>
          <Button variant="outline" size="sm" className="mt-2 w-full">
            Upgrade Plan
          </Button>
        </div>
      </div>
    </div>
  );
}
