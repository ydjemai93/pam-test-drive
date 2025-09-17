import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AGENTS_DATA } from "@/polymet/data/agents-data";
import { PhoneIcon, ArrowLeftIcon } from "lucide-react";

export default function AgentDetailsPage() {
  const { agentId = "1" } = useParams();
  const [isEditing, setIsEditing] = useState(false);
  const [agent, setAgent] = useState(null);

  // Form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [sttModel, setSttModel] = useState("");
  const [ttsModel, setTtsModel] = useState("");
  const [language, setLanguage] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    // Find agent by ID
    const foundAgent = AGENTS_DATA.find((a) => a.id === parseInt(agentId));

    if (foundAgent) {
      setAgent(foundAgent);

      // Initialize form state
      setName(foundAgent.name);
      setDescription(foundAgent.description);
      setSystemPrompt(
        "You are a helpful AI assistant that specializes in " +
          foundAgent.type.toLowerCase() +
          " tasks."
      );
      setLlmModel(foundAgent.type === "Support" ? "gpt-4" : "gpt-3.5-turbo");
      setSttModel("whisper");
      setTtsModel("elevenlabs");
      setLanguage("en-us");
      setType(foundAgent.type);
      setStatus(foundAgent.status);
    }
  }, [agentId]);

  const handleSave = () => {
    // In a real app, this would save to the backend
    setIsEditing(false);
    // Update the local agent state to reflect changes
    setAgent((prev) => ({
      ...prev,
      name,
      description,
      type,
      status,
    }));
  };

  const getStatusColor = (status) => {
    switch (status) {
      case "active":
        return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
      case "draft":
        return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400";
      case "paused":
        return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400";
      default:
        return "";
    }
  };

  if (!agent) {
    return (
      <div className="flex items-center justify-center h-64">
        <p>Loading agent details...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Link to="/agents">
            <Button variant="ghost" size="icon">
              <ArrowLeftIcon className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Agent Details</h1>
        </div>
        <div className="flex space-x-2">
          {isEditing ? (
            <>
              <Button variant="outline" onClick={() => setIsEditing(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave}>Save Changes</Button>
            </>
          ) : (
            <Button onClick={() => setIsEditing(true)}>Edit Agent</Button>
          )}
        </div>
      </div>

      <div className="flex items-center space-x-4">
        <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
          <PhoneIcon className="h-6 w-6 text-primary" />
        </div>
        {isEditing ? (
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="text-2xl font-semibold w-auto"
          />
        ) : (
          <h2 className="text-2xl font-semibold">{agent.name}</h2>
        )}
        <Badge
          variant="secondary"
          className={`capitalize ${getStatusColor(agent.status)}`}
        >
          {agent.status}
        </Badge>
      </div>

      <Tabs defaultValue="settings" className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="settings">Settings</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="history">Call History</TabsTrigger>
        </TabsList>
        <TabsContent value="settings">
          <Card>
            <CardHeader>
              <CardTitle>Agent Configuration</CardTitle>
              <CardDescription>
                Configure your AI agent's capabilities and behavior
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Basic Information */}
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                {isEditing ? (
                  <Textarea
                    id="description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="min-h-[80px] resize-y"
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">{description}</p>
                )}
              </div>

              {/* Type */}
              <div className="space-y-2">
                <Label htmlFor="type">Agent Type</Label>
                {isEditing ? (
                  <Select value={type} onValueChange={setType}>
                    <SelectTrigger id="type">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Support">Support</SelectItem>
                      <SelectItem value="Sales">Sales</SelectItem>
                      <SelectItem value="Scheduling">Scheduling</SelectItem>
                      <SelectItem value="Research">Research</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm">{type}</p>
                )}
              </div>

              {/* Status */}
              <div className="space-y-2">
                <Label htmlFor="status">Status</Label>
                {isEditing ? (
                  <Select value={status} onValueChange={setStatus}>
                    <SelectTrigger id="status">
                      <SelectValue placeholder="Select status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="draft">Draft</SelectItem>
                      <SelectItem value="paused">Paused</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge
                    variant="secondary"
                    className={`capitalize ${getStatusColor(agent.status)}`}
                  >
                    {agent.status}
                  </Badge>
                )}
              </div>

              {/* System Prompt */}
              <div className="space-y-2">
                <Label htmlFor="system-prompt">System Prompt</Label>
                {isEditing ? (
                  <Textarea
                    id="system-prompt"
                    placeholder="You are a helpful AI assistant that..."
                    className="min-h-[120px] resize-y"
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                  />
                ) : (
                  <div className="p-3 bg-muted rounded-md text-sm">
                    {systemPrompt}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Define how your agent should behave and respond
                </p>
              </div>

              {/* Models */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="llm-model">Language Model (LLM)</Label>
                  {isEditing ? (
                    <Select value={llmModel} onValueChange={setLlmModel}>
                      <SelectTrigger id="llm-model">
                        <SelectValue placeholder="Select LLM model" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="gpt-4">GPT-4</SelectItem>
                        <SelectItem value="gpt-3.5-turbo">
                          GPT-3.5 Turbo
                        </SelectItem>
                        <SelectItem value="claude-3">Claude 3</SelectItem>
                        <SelectItem value="llama-3">Llama 3</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-sm">{llmModel}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="stt-model">Speech-to-Text Model</Label>
                  {isEditing ? (
                    <Select value={sttModel} onValueChange={setSttModel}>
                      <SelectTrigger id="stt-model">
                        <SelectValue placeholder="Select STT model" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="whisper">Whisper</SelectItem>
                        <SelectItem value="deepgram">Deepgram</SelectItem>
                        <SelectItem value="assembly-ai">Assembly AI</SelectItem>
                        <SelectItem value="google-stt">Google STT</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-sm">{sttModel}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="tts-model">Text-to-Speech Model</Label>
                  {isEditing ? (
                    <Select value={ttsModel} onValueChange={setTtsModel}>
                      <SelectTrigger id="tts-model">
                        <SelectValue placeholder="Select TTS model" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="elevenlabs">ElevenLabs</SelectItem>
                        <SelectItem value="openai-tts">OpenAI TTS</SelectItem>
                        <SelectItem value="amazon-polly">
                          Amazon Polly
                        </SelectItem>
                        <SelectItem value="google-tts">Google TTS</SelectItem>
                        <SelectItem value="cartesia">Cartesia</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-sm">{ttsModel}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="language">Language</Label>
                  {isEditing ? (
                    <Select value={language} onValueChange={setLanguage}>
                      <SelectTrigger id="language">
                        <SelectValue placeholder="Select language" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="en-us">English (US)</SelectItem>
                        <SelectItem value="en-gb">English (UK)</SelectItem>
                        <SelectItem value="es">Spanish</SelectItem>
                        <SelectItem value="fr">French</SelectItem>
                        <SelectItem value="de">German</SelectItem>
                        <SelectItem value="ja">Japanese</SelectItem>
                        <SelectItem value="zh">Chinese</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-sm">
                      {language === "en-us"
                        ? "English (US)"
                        : language === "en-gb"
                          ? "English (UK)"
                          : language === "es"
                            ? "Spanish"
                            : language === "fr"
                              ? "French"
                              : language === "de"
                                ? "German"
                                : language === "ja"
                                  ? "Japanese"
                                  : language === "zh"
                                    ? "Chinese"
                                    : language}
                    </p>
                  )}
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t">
                <div>
                  <p className="text-sm text-muted-foreground">Total Calls</p>
                  <p className="text-lg font-medium">{agent.calls}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Last Modified</p>
                  <p className="text-lg font-medium">{agent.lastModified}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="text-lg font-medium">{agent.createdAt}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="performance">
          <Card>
            <CardHeader>
              <CardTitle>Performance Metrics</CardTitle>
              <CardDescription>
                View this agent's performance statistics
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center p-12">
                <p className="text-muted-foreground">
                  Performance metrics will be available here
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle>Call History</CardTitle>
              <CardDescription>
                Recent calls handled by this agent
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center p-12">
                <p className="text-muted-foreground">
                  Call history will be displayed here
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
