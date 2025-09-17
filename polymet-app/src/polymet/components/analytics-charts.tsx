import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
} from "recharts";
import {
  DailyCallStats,
  AgentPerformance,
  CallOutcomeDistribution,
  HourlyCallDistribution,
  CallTagDistribution,
} from "@/polymet/data/analytics-data";

interface AnalyticsChartsProps {
  dailyStats: DailyCallStats[];
  agentPerformance: AgentPerformance[];
  callOutcomeDistribution: CallOutcomeDistribution;
  hourlyCallDistribution: HourlyCallDistribution[];
  callTagDistribution: CallTagDistribution[];
}

export function AnalyticsCharts({
  dailyStats,
  agentPerformance,
  callOutcomeDistribution,
  hourlyCallDistribution,
  callTagDistribution,
}: AnalyticsChartsProps) {
  const [timeRange, setTimeRange] = useState("30d");

  // Format the data for the charts
  const callVolumeData = dailyStats.map((day) => ({
    date: day.date,
    total: day.totalCalls,
    completed: day.completedCalls,
    missed: day.missedCalls,
    voicemail: day.voicemails,
  }));

  const agentPerformanceData = agentPerformance.map((agent) => ({
    name: agent.agentName,
    calls: agent.totalCalls,
    conversion: agent.conversionRate,
  }));

  const outcomeData = [
    { name: "Conversion", value: callOutcomeDistribution.conversion },
    { name: "Follow-up", value: callOutcomeDistribution.followUp },
    { name: "No Interest", value: callOutcomeDistribution.noInterest },
    { name: "Information", value: callOutcomeDistribution.information },
  ];

  const hourlyData = hourlyCallDistribution.map((hour) => ({
    hour: hour.hour,
    calls: hour.calls,
  }));

  const tagData = callTagDistribution.slice(0, 8).map((tag) => ({
    name: tag.tag,
    value: tag.count,
  }));

  const COLORS = [
    "hsl(var(--chart-1))",
    "hsl(var(--chart-2))",
    "hsl(var(--chart-3))",
    "hsl(var(--chart-4))",
    "hsl(var(--chart-5))",
  ];

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card className="col-span-2">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle>Call Volume</CardTitle>
          <Tabs
            defaultValue="30d"
            value={timeRange}
            onValueChange={setTimeRange}
          >
            <TabsList>
              <TabsTrigger value="7d">7 days</TabsTrigger>
              <TabsTrigger value="30d">30 days</TabsTrigger>
              <TabsTrigger value="90d">90 days</TabsTrigger>
            </TabsList>
          </Tabs>
        </CardHeader>
        <CardContent>
          <div className="h-[300px]">
            <ChartContainer config={{}} className="aspect-[none] h-[300px]">
              <LineChart data={callVolumeData.slice(-parseInt(timeRange))}>
                <ChartTooltip content={<ChartTooltipContent />} />
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  minTickGap={32}
                  tickFormatter={(value) => {
                    const date = new Date(value);
                    return date.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    });
                  }}
                />

                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="hsl(var(--chart-1))"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                  name="Total Calls"
                />

                <Line
                  type="monotone"
                  dataKey="completed"
                  stroke="hsl(var(--chart-2))"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                  name="Completed"
                />

                <Line
                  type="monotone"
                  dataKey="missed"
                  stroke="hsl(var(--chart-3))"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                  name="Missed"
                />

                <Line
                  type="monotone"
                  dataKey="voicemail"
                  stroke="hsl(var(--chart-4))"
                  strokeWidth={2}
                  dot={false}
                  radius={4}
                  name="Voicemail"
                />
              </LineChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Agent Performance</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px]">
            <ChartContainer config={{}} className="aspect-[none] h-[300px]">
              <BarChart data={agentPerformanceData}>
                <ChartTooltip content={<ChartTooltipContent />} />
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="name"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                />

                <Bar
                  dataKey="calls"
                  fill="hsl(var(--chart-1))"
                  radius={4}
                  name="Total Calls"
                />
              </BarChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Call Outcomes</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center">
            <ChartContainer config={{}} className="aspect-[none] h-[300px]">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent />} />
                <Pie
                  data={outcomeData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                  label={(entry) => entry.name}
                  labelLine={false}
                >
                  {outcomeData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Hourly Call Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px]">
            <ChartContainer config={{}} className="aspect-[none] h-[300px]">
              <BarChart data={hourlyData}>
                <ChartTooltip content={<ChartTooltipContent />} />
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="hour"
                  tickLine={false}
                  axisLine={false}
                  tickMargin={8}
                  tickFormatter={(value) => `${value}:00`}
                />

                <Bar
                  dataKey="calls"
                  fill="hsl(var(--chart-2))"
                  radius={4}
                  name="Calls"
                />
              </BarChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Popular Call Tags</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px]">
            <ChartContainer config={{}} className="aspect-[none] h-[300px]">
              <BarChart data={tagData} layout="vertical">
                <ChartTooltip content={<ChartTooltipContent />} />
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickLine={false} axisLine={false} />
                <Bar
                  dataKey="value"
                  fill="hsl(var(--chart-3))"
                  radius={4}
                  name="Count"
                />
              </BarChart>
            </ChartContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default AnalyticsCharts;
