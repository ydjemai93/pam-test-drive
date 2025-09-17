import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { AreaChart, Area, XAxis, CartesianGrid } from "recharts";
import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";
import { DailyCallStats } from "@/polymet/data/analytics-data";

interface AnalyticsOverviewProps {
  dailyStats: DailyCallStats[];
  totalCalls: number;
  callsChange: {
    value: number;
    trend: "up" | "down";
  };
  conversionRate: number;
  conversionChange: {
    value: number;
    trend: "up" | "down";
  };
  avgDuration: string;
  durationChange: {
    value: string;
    trend: "up" | "down";
  };
}

export function AnalyticsOverview({
  dailyStats,
  totalCalls,
  callsChange,
  conversionRate,
  conversionChange,
  avgDuration,
  durationChange,
}: AnalyticsOverviewProps) {
  // Format the data for the chart
  const chartData = dailyStats.map((day) => ({
    date: day.date,
    calls: day.totalCalls,
  }));

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Calls</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {totalCalls.toLocaleString()}
          </div>
          <div className="flex items-center text-xs">
            {callsChange.trend === "up" ? (
              <ArrowUpIcon className="h-4 w-4 text-green-500 mr-1" />
            ) : (
              <ArrowDownIcon className="h-4 w-4 text-red-500 mr-1" />
            )}
            <span
              className={
                callsChange.trend === "up" ? "text-green-500" : "text-red-500"
              }
            >
              {callsChange.value > 0 ? "+" : ""}
              {callsChange.value}%
            </span>
            <span className="text-muted-foreground ml-1">last month</span>
          </div>
          <div className="h-[50px] mt-4">
            <ChartContainer config={{}} className="aspect-[none]">
              <AreaChart width={250} height={50} data={chartData}>
                <ChartTooltip content={<ChartTooltipContent />} />
                <defs>
                  <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="5%"
                      stopColor="hsl(var(--chart-1))"
                      stopOpacity={0.8}
                    />

                    <stop
                      offset="95%"
                      stopColor="hsl(var(--chart-1))"
                      stopOpacity={0.1}
                    />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="calls"
                  stroke="hsl(var(--chart-1))"
                  fill="url(#colorCalls)"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                />
              </AreaChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Conversion Rate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{conversionRate}%</div>
          <div className="flex items-center text-xs">
            {conversionChange.trend === "up" ? (
              <ArrowUpIcon className="h-4 w-4 text-green-500 mr-1" />
            ) : (
              <ArrowDownIcon className="h-4 w-4 text-red-500 mr-1" />
            )}
            <span
              className={
                conversionChange.trend === "up"
                  ? "text-green-500"
                  : "text-red-500"
              }
            >
              {conversionChange.value > 0 ? "+" : ""}
              {conversionChange.value}%
            </span>
            <span className="text-muted-foreground ml-1">last month</span>
          </div>
          <div className="h-[50px] mt-4">
            <ChartContainer config={{}} className="aspect-[none]">
              <AreaChart
                width={250}
                height={50}
                data={chartData.map((day) => ({
                  ...day,
                  conversion: dailyStats.find((d) => d.date === day.date)
                    ?.conversionRate,
                }))}
              >
                <ChartTooltip content={<ChartTooltipContent />} />
                <defs>
                  <linearGradient
                    id="colorConversion"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="5%"
                      stopColor="hsl(var(--chart-2))"
                      stopOpacity={0.8}
                    />

                    <stop
                      offset="95%"
                      stopColor="hsl(var(--chart-2))"
                      stopOpacity={0.1}
                    />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="conversion"
                  stroke="hsl(var(--chart-2))"
                  fill="url(#colorConversion)"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                />
              </AreaChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">
            Avg. Call Duration
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{avgDuration}</div>
          <div className="flex items-center text-xs">
            {durationChange.trend === "up" ? (
              <ArrowUpIcon className="h-4 w-4 text-red-500 mr-1" />
            ) : (
              <ArrowDownIcon className="h-4 w-4 text-green-500 mr-1" />
            )}
            <span
              className={
                durationChange.trend === "up"
                  ? "text-red-500"
                  : "text-green-500"
              }
            >
              {durationChange.trend === "up" ? "+" : "-"}
              {durationChange.value}
            </span>
            <span className="text-muted-foreground ml-1">last month</span>
          </div>
          <div className="h-[50px] mt-4">
            <ChartContainer config={{}} className="aspect-[none]">
              <AreaChart
                width={250}
                height={50}
                data={chartData.map((day) => ({
                  ...day,
                  duration: dailyStats.find((d) => d.date === day.date)
                    ?.averageDuration,
                }))}
              >
                <ChartTooltip content={<ChartTooltipContent />} />
                <defs>
                  <linearGradient
                    id="colorDuration"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="5%"
                      stopColor="hsl(var(--chart-3))"
                      stopOpacity={0.8}
                    />

                    <stop
                      offset="95%"
                      stopColor="hsl(var(--chart-3))"
                      stopOpacity={0.1}
                    />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="duration"
                  stroke="hsl(var(--chart-3))"
                  fill="url(#colorDuration)"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                />
              </AreaChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">
            Call Completion Rate
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {Math.round(
              (dailyStats.reduce((acc, day) => acc + day.completedCalls, 0) /
                dailyStats.reduce((acc, day) => acc + day.totalCalls, 0)) *
                100
            )}
            %
          </div>
          <div className="flex items-center text-xs">
            <ArrowUpIcon className="h-4 w-4 text-green-500 mr-1" />
            <span className="text-green-500">+2.5%</span>
            <span className="text-muted-foreground ml-1">last month</span>
          </div>
          <div className="h-[50px] mt-4">
            <ChartContainer config={{}} className="aspect-[none]">
              <AreaChart
                width={250}
                height={50}
                data={chartData.map((day) => {
                  const stat = dailyStats.find((d) => d.date === day.date);
                  return {
                    ...day,
                    completion: stat
                      ? (stat.completedCalls / stat.totalCalls) * 100
                      : 0,
                  };
                })}
              >
                <ChartTooltip content={<ChartTooltipContent />} />
                <defs>
                  <linearGradient
                    id="colorCompletion"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="5%"
                      stopColor="hsl(var(--chart-4))"
                      stopOpacity={0.8}
                    />

                    <stop
                      offset="95%"
                      stopColor="hsl(var(--chart-4))"
                      stopOpacity={0.1}
                    />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="completion"
                  stroke="hsl(var(--chart-4))"
                  fill="url(#colorCompletion)"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                />
              </AreaChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default AnalyticsOverview;
