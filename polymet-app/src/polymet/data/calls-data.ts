export interface Call {
  id: string;
  agentName: string;
  agentId: number;
  customerName: string;
  customerId: number;
  phoneNumber: string;
  duration: string; // in format "m:ss"
  durationSeconds: number;
  status: "completed" | "missed" | "voicemail" | "ongoing";
  timestamp: string;
  recordingUrl?: string;
  notes?: string;
  tags?: string[];
  outcome?: "conversion" | "follow-up" | "no-interest" | "information";
}

export const CALLS_DATA: Call[] = [
  {
    id: "call-001",
    agentName: "Customer Support Agent",
    agentId: 1,
    customerName: "John Smith",
    customerId: 101,
    phoneNumber: "+1 (555) 123-4567",
    duration: "4:32",
    durationSeconds: 272,
    status: "completed",
    timestamp: "2023-11-28T14:30:00Z",
    recordingUrl: "https://example.com/recordings/call-001.mp3",
    notes: "Customer inquired about premium plan features",
    tags: ["billing", "upgrade"],
    outcome: "conversion",
  },
  {
    id: "call-002",
    agentName: "Sales Representative",
    agentId: 2,
    customerName: "Emily Johnson",
    customerId: 102,
    phoneNumber: "+1 (555) 234-5678",
    duration: "6:15",
    durationSeconds: 375,
    status: "completed",
    timestamp: "2023-11-28T15:45:00Z",
    recordingUrl: "https://example.com/recordings/call-002.mp3",
    notes: "Scheduled a demo for next Tuesday",
    tags: ["demo", "enterprise"],
    outcome: "follow-up",
  },
  {
    id: "call-003",
    agentName: "Appointment Scheduler",
    agentId: 3,
    customerName: "Michael Brown",
    customerId: 103,
    phoneNumber: "+1 (555) 345-6789",
    duration: "2:48",
    durationSeconds: 168,
    status: "completed",
    timestamp: "2023-11-28T16:20:00Z",
    recordingUrl: "https://example.com/recordings/call-003.mp3",
    notes: "Confirmed appointment for service installation",
    tags: ["appointment", "installation"],
    outcome: "conversion",
  },
  {
    id: "call-004",
    agentName: "Customer Support Agent",
    agentId: 1,
    customerName: "Sarah Davis",
    customerId: 104,
    phoneNumber: "+1 (555) 456-7890",
    duration: "0:00",
    durationSeconds: 0,
    status: "missed",
    timestamp: "2023-11-28T17:05:00Z",
    tags: ["missed"],
  },
  {
    id: "call-005",
    agentName: "Sales Representative",
    agentId: 2,
    customerName: "Robert Wilson",
    customerId: 105,
    phoneNumber: "+1 (555) 567-8901",
    duration: "5:23",
    durationSeconds: 323,
    status: "completed",
    timestamp: "2023-11-28T09:15:00Z",
    recordingUrl: "https://example.com/recordings/call-005.mp3",
    notes: "Customer interested in enterprise plan",
    tags: ["enterprise", "pricing"],
    outcome: "follow-up",
  },
  {
    id: "call-006",
    agentName: "Appointment Scheduler",
    agentId: 3,
    customerName: "Jennifer Taylor",
    customerId: 106,
    phoneNumber: "+1 (555) 678-9012",
    duration: "1:47",
    durationSeconds: 107,
    status: "completed",
    timestamp: "2023-11-28T10:30:00Z",
    recordingUrl: "https://example.com/recordings/call-006.mp3",
    notes: "Rescheduled appointment to next week",
    tags: ["appointment", "reschedule"],
    outcome: "conversion",
  },
  {
    id: "call-007",
    agentName: "Customer Support Agent",
    agentId: 1,
    customerName: "David Anderson",
    customerId: 107,
    phoneNumber: "+1 (555) 789-0123",
    duration: "0:45",
    durationSeconds: 45,
    status: "voicemail",
    timestamp: "2023-11-28T11:20:00Z",
    notes: "Left voicemail about account update",
    tags: ["account", "voicemail"],
  },
  {
    id: "call-008",
    agentName: "Sales Representative",
    agentId: 2,
    customerName: "Lisa Martinez",
    customerId: 108,
    phoneNumber: "+1 (555) 890-1234",
    duration: "8:12",
    durationSeconds: 492,
    status: "completed",
    timestamp: "2023-11-27T13:45:00Z",
    recordingUrl: "https://example.com/recordings/call-008.mp3",
    notes: "Detailed discussion about integration options",
    tags: ["integration", "technical"],
    outcome: "conversion",
  },
  {
    id: "call-009",
    agentName: "Appointment Scheduler",
    agentId: 3,
    customerName: "Kevin Thompson",
    customerId: 109,
    phoneNumber: "+1 (555) 901-2345",
    duration: "2:05",
    durationSeconds: 125,
    status: "completed",
    timestamp: "2023-11-27T14:30:00Z",
    recordingUrl: "https://example.com/recordings/call-009.mp3",
    notes: "Scheduled initial consultation",
    tags: ["appointment", "consultation"],
    outcome: "conversion",
  },
  {
    id: "call-010",
    agentName: "Customer Support Agent",
    agentId: 1,
    customerName: "Amanda White",
    customerId: 110,
    phoneNumber: "+1 (555) 012-3456",
    duration: "3:38",
    durationSeconds: 218,
    status: "completed",
    timestamp: "2023-11-27T15:15:00Z",
    recordingUrl: "https://example.com/recordings/call-010.mp3",
    notes: "Resolved billing issue",
    tags: ["billing", "support"],
    outcome: "information",
  },
  {
    id: "call-011",
    agentName: "Sales Representative",
    agentId: 2,
    customerName: "Thomas Harris",
    customerId: 111,
    phoneNumber: "+1 (555) 123-4567",
    duration: "4:20",
    durationSeconds: 260,
    status: "completed",
    timestamp: "2023-11-27T16:00:00Z",
    recordingUrl: "https://example.com/recordings/call-011.mp3",
    notes: "Customer decided not to proceed with purchase",
    tags: ["sales", "declined"],
    outcome: "no-interest",
  },
  {
    id: "call-012",
    agentName: "Customer Support Agent",
    agentId: 1,
    customerName: "Nicole Clark",
    customerId: 112,
    phoneNumber: "+1 (555) 234-5678",
    duration: "5:52",
    durationSeconds: 352,
    status: "completed",
    timestamp: "2023-11-26T10:20:00Z",
    recordingUrl: "https://example.com/recordings/call-012.mp3",
    notes: "Provided tutorial on new features",
    tags: ["onboarding", "training"],
    outcome: "information",
  },
  {
    id: "call-013",
    agentName: "Sales Representative",
    agentId: 2,
    customerName: "Daniel Lewis",
    customerId: 113,
    phoneNumber: "+1 (555) 345-6789",
    duration: "7:15",
    durationSeconds: 435,
    status: "completed",
    timestamp: "2023-11-26T11:30:00Z",
    recordingUrl: "https://example.com/recordings/call-013.mp3",
    notes: "Discussed custom pricing options",
    tags: ["pricing", "enterprise"],
    outcome: "follow-up",
  },
  {
    id: "call-014",
    agentName: "Appointment Scheduler",
    agentId: 3,
    customerName: "Michelle Walker",
    customerId: 114,
    phoneNumber: "+1 (555) 456-7890",
    duration: "1:30",
    durationSeconds: 90,
    status: "completed",
    timestamp: "2023-11-26T13:45:00Z",
    recordingUrl: "https://example.com/recordings/call-014.mp3",
    notes: "Scheduled product demo",
    tags: ["appointment", "demo"],
    outcome: "conversion",
  },
  {
    id: "call-015",
    agentName: "Customer Support Agent",
    agentId: 1,
    customerName: "Christopher Hall",
    customerId: 115,
    phoneNumber: "+1 (555) 567-8901",
    duration: "3:25",
    durationSeconds: 205,
    status: "completed",
    timestamp: "2023-11-26T14:50:00Z",
    recordingUrl: "https://example.com/recordings/call-015.mp3",
    notes: "Troubleshot login issues",
    tags: ["technical", "login"],
    outcome: "information",
  },
];

// Helper function to get calls for a specific agent
export const getCallsByAgent = (agentId: number): Call[] => {
  return CALLS_DATA.filter((call) => call.agentId === agentId);
};

// Helper function to get calls for a specific customer
export const getCallsByCustomer = (customerId: number): Call[] => {
  return CALLS_DATA.filter((call) => call.customerId === customerId);
};

// Helper function to get calls by status
export const getCallsByStatus = (status: Call["status"]): Call[] => {
  return CALLS_DATA.filter((call) => call.status === status);
};

// Helper function to get calls by date range
export const getCallsByDateRange = (
  startDate: string,
  endDate: string
): Call[] => {
  const start = new Date(startDate).getTime();
  const end = new Date(endDate).getTime();

  return CALLS_DATA.filter((call) => {
    const callTime = new Date(call.timestamp).getTime();
    return callTime >= start && callTime <= end;
  });
};
