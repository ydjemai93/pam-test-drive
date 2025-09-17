import React from "react";
import { StatsCard } from "@/polymet/components/stats-card";
import { Button } from "@/components/ui/button";
import { PlusIcon } from "lucide-react";
import { Link } from "react-router-dom";

export default function Dashboard() {
  const stats = [
    { title: "Total Calls", value: "1,284", change: "+12.5%", trend: "up" },
    { title: "Active Agents", value: "7", change: "+2", trend: "up" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Welcome back! Here's an overview of your AI agents.
          </p>
        </div>
        <Link to="/create-agent">
          <Button className="gap-2">
            <PlusIcon className="h-4 w-4" />
            New Agent
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {stats.map((stat, index) => (
          <StatsCard key={index} {...stat} />
        ))}
      </div>
    </div>
  );
}
