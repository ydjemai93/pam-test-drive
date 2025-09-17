import React from "react";
import { Sidebar } from "@/polymet/components/sidebar";
import { ThemeToggle } from "@/polymet/components/theme-toggle";
import { BellIcon, SearchIcon, UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

interface LayoutProps {
  children: React.ReactNode;
  currentPage: string;
  setCurrentPage: (page: string) => void;
}

export default function Layout({
  children,
  currentPage,
  setCurrentPage,
}: LayoutProps) {
  return (
    <div className="flex h-screen bg-background" id="31epo1">
      <Sidebar
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        id="lhik0s"
      />

      <div className="flex flex-col flex-1 overflow-hidden" id="6tzepj">
        <header
          className="flex items-center justify-between px-6 py-4 border-b"
          id="ow8h9t"
        >
          <div className="flex items-center w-1/3" id="w4j6ez">
            <div className="relative w-full max-w-md" id="yfiydl">
              <SearchIcon
                className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground"
                id="uyvoet"
              />

              <Input
                type="search"
                placeholder="Search agents, calls, analytics..."
                className="pl-8 w-full bg-muted/30"
                id="9xwd8j"
              />
            </div>
          </div>

          <div className="flex items-center space-x-4" id="yag945">
            <ThemeToggle id="cts0do" />
            <Button
              variant="outline"
              size="icon"
              className="relative"
              id="lpxft2"
            >
              <BellIcon className="h-5 w-5" id="okb3wm" />
              <span
                className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-primary text-[10px] font-medium text-primary-foreground flex items-center justify-center"
                id="jdsl4s"
              >
                3
              </span>
            </Button>
            <div className="flex items-center space-x-2" id="stf9te">
              <Avatar id="yj2gkd">
                <AvatarImage
                  src="https://github.com/yusufhilmi.png"
                  alt="User"
                  id="r4hr5u"
                />

                <AvatarFallback id="yy6xhv">YH</AvatarFallback>
              </Avatar>
              <div className="hidden md:block" id="8u7jc9">
                <p className="text-sm font-medium" id="lut5dh">
                  Yusuf Hilmi
                </p>
                <p className="text-xs text-muted-foreground" id="ifh41u">
                  Admin
                </p>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6" id="6gc0nf">
          {children}
        </main>
      </div>
    </div>
  );
}
