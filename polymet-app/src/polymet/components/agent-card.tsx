import React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  PhoneIcon,
  EditIcon,
  MoreHorizontalIcon,
  PauseIcon,
  TrashIcon,
  CopyIcon,
  BarChartIcon,
} from "lucide-react";

interface AgentProps {
  agent: {
    id: number;
    name: string;
    description: string;
    calls: number;
    avgRating: number;
    status: string;
    lastModified: string;
  };
}

export function AgentCard({ agent }: AgentProps) {
  return (
    <Card className="overflow-hidden border border-muted" id="w24luk">
      <div className="flex flex-col md:flex-row" id="8ffoqt">
        <div className="flex-1 p-6" id="j18h3o">
          <div className="flex items-center justify-between" id="0s06vp">
            <div className="flex items-center space-x-2" id="coz6jn">
              <div
                className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center"
                id="yrsw4k"
              >
                <PhoneIcon className="h-5 w-5 text-primary" id="w26p62" />
              </div>
              <div id="rwiihp">
                <h3 className="font-semibold" id="b4m1gw">
                  {agent.name}
                </h3>
                <p className="text-sm text-muted-foreground" id="jw0gma">
                  Last modified: {agent.lastModified}
                </p>
              </div>
            </div>
            <Badge
              variant={agent.status === "active" ? "default" : "secondary"}
              className="capitalize"
              id="4c9idz"
            >
              {agent.status}
            </Badge>
          </div>

          <p className="mt-3 text-sm text-muted-foreground" id="qhlaq9">
            {agent.description}
          </p>

          <div className="mt-4 flex items-center space-x-4 text-sm" id="zs8g4d">
            <div className="flex items-center" id="4f1ky9">
              <PhoneIcon
                className="mr-1 h-4 w-4 text-muted-foreground"
                id="01s4kv"
              />

              <span id="9y85as">{agent.calls} calls</span>
            </div>
          </div>
        </div>

        <div
          className="flex flex-row md:flex-col justify-between border-t md:border-l md:border-t-0 bg-muted/30 p-4"
          id="0qeaty"
        >
          <Button variant="ghost" size="icon" id="hzgizv">
            <EditIcon className="h-4 w-4" id="07rluk" />

            <span className="sr-only" id="ifhhfm">
              Edit
            </span>
          </Button>
          <Button variant="ghost" size="icon" id="iivfl6">
            <BarChartIcon className="h-4 w-4" id="cg247j" />

            <span className="sr-only" id="ksm64o">
              Analytics
            </span>
          </Button>
          <Button variant="ghost" size="icon" id="zqak94">
            <PauseIcon className="h-4 w-4" id="ze9v5r" />

            <span className="sr-only" id="g1ffqj">
              Pause
            </span>
          </Button>
          <DropdownMenu id="mxpq7c">
            <DropdownMenuTrigger asChild id="bo6f38">
              <Button variant="ghost" size="icon" id="259mcc">
                <MoreHorizontalIcon className="h-4 w-4" id="up2u8b" />

                <span className="sr-only" id="8sdrg5">
                  More
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" id="viwsj8">
              <DropdownMenuItem id="r7p92y">
                <CopyIcon className="mr-2 h-4 w-4" id="81xwu3" />

                <span id="wzlcr3">Duplicate</span>
              </DropdownMenuItem>
              <DropdownMenuItem id="4ljcyl">
                <TrashIcon className="mr-2 h-4 w-4" id="smxtcr" />

                <span id="79e3ni">Delete</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </Card>
  );
}
