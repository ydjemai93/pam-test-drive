import React from "react";
import { SidebarWithRouter } from "@/polymet/components/sidebar-with-router";
import { ThemeToggle } from "@/polymet/components/theme-toggle";
import { Link } from "react-router-dom";
import { BellIcon, SearchIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

interface LayoutWithRouterProps {
  children: React.ReactNode;
}

export function LayoutWithRouter({ children }: LayoutWithRouterProps) {
  return (
    <div className="flex h-screen bg-background">
      <SidebarWithRouter />

      <div className="flex flex-col flex-1 overflow-hidden">
        <header className="flex items-center justify-between px-6 py-4 border-b">
          <div className="flex items-center w-1/3">
            <div className="relative w-full max-w-md">
              <SearchIcon className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />

              <Input
                type="search"
                placeholder="Search agents, calls, analytics..."
                className="pl-8 w-full bg-muted/30"
              />
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <ThemeToggle />
            <Button variant="outline" size="icon" className="relative">
              <BellIcon className="h-5 w-5" />

              <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-primary text-[10px] font-medium text-primary-foreground flex items-center justify-center">
                3
              </span>
            </Button>
            <div className="flex items-center space-x-2">
              <Avatar>
                <AvatarImage
                  src="https://github.com/yusufhilmi.png"
                  alt="User"
                />

                <AvatarFallback>YH</AvatarFallback>
              </Avatar>
              <div className="hidden md:block">
                <p className="text-sm font-medium">Yusuf Hilmi</p>
                <p className="text-xs text-muted-foreground">Admin</p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
