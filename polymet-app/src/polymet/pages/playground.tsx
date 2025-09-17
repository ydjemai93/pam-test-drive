import React, { useState } from "react";
import { Link } from "react-router-dom";
import { AGENTS_DATA, Agent } from "@/polymet/data/agents-data";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { toast } from "@/polymet/components/sonner";
import { PhoneIcon, InfoIcon } from "lucide-react";
import PhoneInput from "@/polymet/components/phone-input";
import AgentSelector from "@/polymet/components/agent-selector";

export default function PlaygroundPage() {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [phoneError, setPhoneError] = useState("");

  // Filter to only show active agents
  const activeAgents = AGENTS_DATA.filter((agent) => agent.status === "active");

  const validatePhoneNumber = (phone: string) => {
    // Simple validation - check if it's a complete US phone number
    const phoneRegex = /^\(\d{3}\) \d{3}-\d{4}$/;
    return phoneRegex.test(phone);
  };

  const handleStartCall = () => {
    if (!selectedAgent) {
      toast.error("Please select an agent");
      return;
    }

    if (!validatePhoneNumber(phoneNumber)) {
      setPhoneError("Please enter a valid phone number");
      return;
    }

    setPhoneError("");
    toast.success("Call initiated successfully");

    // In a real implementation, this would connect to a backend service
    // to initiate the call with the selected agent and phone number
  };

  return (
    <div className="container mx-auto py-6 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Playground</h1>
          <p className="text-muted-foreground">
            Test your AI agents with real phone calls
          </p>
        </div>
      </div>

      <div className="w-full mt-6">
        <div className="max-w-2xl mx-auto">
          <Card>
            <CardHeader>
              <CardTitle>Call Setup</CardTitle>
              <CardDescription>
                Configure your test call by selecting an agent and entering a
                phone number
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <h3 className="text-sm font-medium">1. Select an AI Agent</h3>
                <AgentSelector
                  agents={AGENTS_DATA}
                  selectedAgent={selectedAgent}
                  onSelect={setSelectedAgent}
                />
              </div>

              <Separator />

              <div className="space-y-4">
                <h3 className="text-sm font-medium">2. Enter Phone Number</h3>
                <PhoneInput
                  value={phoneNumber}
                  onChange={setPhoneNumber}
                  error={phoneError}
                />
              </div>
            </CardContent>
            <CardFooter className="flex justify-between">
              <Link to="/agents">
                <Button variant="outline">View All Agents</Button>
              </Link>
              <Button
                onClick={handleStartCall}
                disabled={!selectedAgent}
                className="gap-2"
              >
                <PhoneIcon className="h-4 w-4" />
                Start Call
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>How It Works</CardTitle>
          <CardDescription>
            Learn how to use the playground to test your AI agents
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <h3 className="font-medium">1. Select an Agent</h3>
              <p className="text-sm text-muted-foreground">
                Choose one of your active AI agents to handle the test call.
              </p>
            </div>
            <div className="space-y-2">
              <h3 className="font-medium">2. Enter a Phone Number</h3>
              <p className="text-sm text-muted-foreground">
                Enter the phone number you want to call for testing purposes.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
