import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";

interface StatsCardProps {
  title: string;
  value: string;
  change: string;
  trend: "up" | "down";
}

export function StatsCard({ title, value, change, trend }: StatsCardProps) {
  return (
    <Card id="g650c9">
      <CardHeader
        className="flex flex-row items-center justify-between space-y-0 pb-2"
        id="0hlcx4"
      >
        <CardTitle className="text-sm font-medium" id="t8kc6r">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent id="mtorrr">
        <div className="text-2xl font-bold" id="qx38pl">
          {value}
        </div>
        <div className="flex items-center text-xs mt-1" id="7042r8">
          {trend === "up" ? (
            <ArrowUpIcon className="h-4 w-4 text-green-500 mr-1" id="notvu3" />
          ) : (
            <ArrowDownIcon className="h-4 w-4 text-red-500 mr-1" id="at1k8q" />
          )}

          <span
            className={trend === "up" ? "text-green-500" : "text-red-500"}
            id="46l1pi"
          >
            {change}
          </span>
          <span className="text-muted-foreground ml-1" id="v74f7k">
            from last month
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
