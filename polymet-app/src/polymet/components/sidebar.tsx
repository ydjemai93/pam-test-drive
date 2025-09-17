import React from "react";
import {
  HomeIcon,
  PhoneIcon,
  SettingsIcon,
  HelpCircleIcon,
  FileTextIcon,
  ZapIcon,
  PlusIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CreateAgentPage } from "@/polymet/components/create-agent-page";

interface SidebarProps {
  currentPage: string;
  setCurrentPage: (page: string) => void;
}

export function Sidebar({ currentPage, setCurrentPage }: SidebarProps) {
  const navItems = [
    {
      name: "Dashboard",
      id: "dashboard",
      icon: HomeIcon,
    },
    {
      name: "AI Agents",
      id: "agents",
      icon: ZapIcon,
    },
    {
      name: "Call History",
      id: "calls",
      icon: PhoneIcon,
    },
  ];

  const secondaryNavItems = [
    {
      name: "Settings",
      id: "settings",
      icon: SettingsIcon,
    },
    {
      name: "Help Center",
      id: "help",
      icon: HelpCircleIcon,
    },
    {
      name: "Documentation",
      id: "docs",
      icon: FileTextIcon,
    },
  ];

  // Define the gradient color for the logo and icons
  const logoGradientClass =
    "text-transparent bg-clip-text bg-gradient-to-b from-[#2E8B57] to-[#7FFF00]";
  const iconGradientClass = "text-[#2E8B57]";

  return (
    <div className="flex h-full flex-col border-r bg-background">
      <div className="flex h-14 items-center border-b px-4">
        <div
          className="flex items-center gap-2 font-semibold cursor-pointer"
          onClick={() => setCurrentPage("dashboard")}
        >
          <ZapIcon className={`h-6 w-6 ${iconGradientClass}`} />

          <span className="text-lg">VoiceGenius</span>
        </div>
      </div>
      <div className="flex-1 overflow-auto py-2">
        <div className="px-3 py-2">
          <Button
            className="w-full justify-start gap-2"
            onClick={() => setCurrentPage("create-agent")}
          >
            <PlusIcon className="h-4 w-4" />
            Create New Agent
          </Button>
        </div>
        <nav className="grid gap-1 px-2 group-[.active]:bg-accent">
          {navItems.map((item) => (
            <div
              key={item.name}
              onClick={() => setCurrentPage(item.id)}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground cursor-pointer",
                currentPage === item.id
                  ? "bg-accent text-accent-foreground"
                  : "transparent"
              )}
            >
              <item.icon
                className={`h-4 w-4 ${currentPage === item.id ? "" : iconGradientClass}`}
              />

              {item.name}
            </div>
          ))}
        </nav>
        <nav className="mt-8 grid gap-1 px-2">
          {secondaryNavItems.map((item) => (
            <div
              key={item.name}
              onClick={() => setCurrentPage(item.id)}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground cursor-pointer",
                currentPage === item.id
                  ? "bg-accent text-accent-foreground"
                  : "transparent"
              )}
            >
              <item.icon
                className={`h-4 w-4 ${currentPage === item.id ? "" : iconGradientClass}`}
              />

              {item.name}
            </div>
          ))}
        </nav>
      </div>
      <div className="mt-auto p-4 border-t">
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
