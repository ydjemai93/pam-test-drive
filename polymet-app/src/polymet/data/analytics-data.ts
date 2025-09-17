export interface DailyCallStats {
  date: string;
  totalCalls: number;
  completedCalls: number;
  missedCalls: number;
  voicemails: number;
  averageDuration: number; // in seconds
  conversionRate: number; // percentage
}

export interface AgentPerformance {
  agentId: number;
  agentName: string;
  totalCalls: number;
  completedCalls: number;
  missedCalls: number;
  averageDuration: number; // in seconds
  conversionRate: number; // percentage
}

export interface CallOutcomeDistribution {
  conversion: number;
  followUp: number;
  noInterest: number;
  information: number;
}

export interface HourlyCallDistribution {
  hour: number; // 0-23
  calls: number;
}

export interface CallTagDistribution {
  tag: string;
  count: number;
}

// Daily call statistics for the past 30 days
export const DAILY_CALL_STATS: DailyCallStats[] = [
  {
    date: "2023-11-28",
    totalCalls: 45,
    completedCalls: 38,
    missedCalls: 4,
    voicemails: 3,
    averageDuration: 245,
    conversionRate: 22,
  },
  {
    date: "2023-11-27",
    totalCalls: 42,
    completedCalls: 35,
    missedCalls: 5,
    voicemails: 2,
    averageDuration: 230,
    conversionRate: 24,
  },
  {
    date: "2023-11-26",
    totalCalls: 38,
    completedCalls: 33,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 255,
    conversionRate: 26,
  },
  {
    date: "2023-11-25",
    totalCalls: 30,
    completedCalls: 25,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 20,
  },
  {
    date: "2023-11-24",
    totalCalls: 48,
    completedCalls: 42,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 235,
    conversionRate: 25,
  },
  {
    date: "2023-11-23",
    totalCalls: 52,
    completedCalls: 45,
    missedCalls: 5,
    voicemails: 2,
    averageDuration: 225,
    conversionRate: 23,
  },
  {
    date: "2023-11-22",
    totalCalls: 44,
    completedCalls: 38,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 250,
    conversionRate: 21,
  },
  {
    date: "2023-11-21",
    totalCalls: 40,
    completedCalls: 34,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 260,
    conversionRate: 22,
  },
  {
    date: "2023-11-20",
    totalCalls: 46,
    completedCalls: 40,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 24,
  },
  {
    date: "2023-11-19",
    totalCalls: 35,
    completedCalls: 30,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 235,
    conversionRate: 23,
  },
  {
    date: "2023-11-18",
    totalCalls: 32,
    completedCalls: 28,
    missedCalls: 2,
    voicemails: 2,
    averageDuration: 245,
    conversionRate: 25,
  },
  {
    date: "2023-11-17",
    totalCalls: 50,
    completedCalls: 43,
    missedCalls: 5,
    voicemails: 2,
    averageDuration: 230,
    conversionRate: 26,
  },
  {
    date: "2023-11-16",
    totalCalls: 48,
    completedCalls: 42,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 24,
  },
  {
    date: "2023-11-15",
    totalCalls: 45,
    completedCalls: 39,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 250,
    conversionRate: 22,
  },
  {
    date: "2023-11-14",
    totalCalls: 42,
    completedCalls: 36,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 255,
    conversionRate: 23,
  },
  {
    date: "2023-11-13",
    totalCalls: 44,
    completedCalls: 38,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 235,
    conversionRate: 25,
  },
  {
    date: "2023-11-12",
    totalCalls: 36,
    completedCalls: 31,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 24,
  },
  {
    date: "2023-11-11",
    totalCalls: 34,
    completedCalls: 29,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 245,
    conversionRate: 22,
  },
  {
    date: "2023-11-10",
    totalCalls: 46,
    completedCalls: 40,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 230,
    conversionRate: 26,
  },
  {
    date: "2023-11-09",
    totalCalls: 50,
    completedCalls: 43,
    missedCalls: 5,
    voicemails: 2,
    averageDuration: 235,
    conversionRate: 25,
  },
  {
    date: "2023-11-08",
    totalCalls: 48,
    completedCalls: 41,
    missedCalls: 5,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 23,
  },
  {
    date: "2023-11-07",
    totalCalls: 44,
    completedCalls: 38,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 250,
    conversionRate: 24,
  },
  {
    date: "2023-11-06",
    totalCalls: 42,
    completedCalls: 36,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 245,
    conversionRate: 22,
  },
  {
    date: "2023-11-05",
    totalCalls: 38,
    completedCalls: 33,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 235,
    conversionRate: 23,
  },
  {
    date: "2023-11-04",
    totalCalls: 36,
    completedCalls: 31,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 25,
  },
  {
    date: "2023-11-03",
    totalCalls: 44,
    completedCalls: 38,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 230,
    conversionRate: 24,
  },
  {
    date: "2023-11-02",
    totalCalls: 46,
    completedCalls: 40,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 235,
    conversionRate: 26,
  },
  {
    date: "2023-11-01",
    totalCalls: 42,
    completedCalls: 36,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 245,
    conversionRate: 23,
  },
  {
    date: "2023-10-31",
    totalCalls: 40,
    completedCalls: 34,
    missedCalls: 4,
    voicemails: 2,
    averageDuration: 250,
    conversionRate: 22,
  },
  {
    date: "2023-10-30",
    totalCalls: 38,
    completedCalls: 33,
    missedCalls: 3,
    voicemails: 2,
    averageDuration: 240,
    conversionRate: 24,
  },
];

// Agent performance metrics
export const AGENT_PERFORMANCE: AgentPerformance[] = [
  {
    agentId: 1,
    agentName: "Customer Support Agent",
    totalCalls: 423,
    completedCalls: 380,
    missedCalls: 25,
    averageDuration: 222,
    conversionRate: 24,
  },
  {
    agentId: 2,
    agentName: "Sales Representative",
    totalCalls: 287,
    completedCalls: 250,
    missedCalls: 20,
    averageDuration: 315,
    conversionRate: 32,
  },
  {
    agentId: 3,
    agentName: "Appointment Scheduler",
    totalCalls: 156,
    completedCalls: 140,
    missedCalls: 10,
    averageDuration: 180,
    conversionRate: 45,
  },
];

// Call outcome distribution
export const CALL_OUTCOME_DISTRIBUTION: CallOutcomeDistribution = {
  conversion: 35,
  followUp: 25,
  noInterest: 15,
  information: 25,
};

// Hourly call distribution
export const HOURLY_CALL_DISTRIBUTION: HourlyCallDistribution[] = [
  { hour: 0, calls: 5 },
  { hour: 1, calls: 3 },
  { hour: 2, calls: 2 },
  { hour: 3, calls: 1 },
  { hour: 4, calls: 1 },
  { hour: 5, calls: 2 },
  { hour: 6, calls: 5 },
  { hour: 7, calls: 15 },
  { hour: 8, calls: 35 },
  { hour: 9, calls: 65 },
  { hour: 10, calls: 85 },
  { hour: 11, calls: 95 },
  { hour: 12, calls: 75 },
  { hour: 13, calls: 85 },
  { hour: 14, calls: 90 },
  { hour: 15, calls: 80 },
  { hour: 16, calls: 70 },
  { hour: 17, calls: 50 },
  { hour: 18, calls: 30 },
  { hour: 19, calls: 20 },
  { hour: 20, calls: 15 },
  { hour: 21, calls: 10 },
  { hour: 22, calls: 8 },
  { hour: 23, calls: 6 },
];

// Call tag distribution
export const CALL_TAG_DISTRIBUTION: CallTagDistribution[] = [
  { tag: "billing", count: 120 },
  { tag: "technical", count: 95 },
  { tag: "appointment", count: 85 },
  { tag: "demo", count: 75 },
  { tag: "pricing", count: 70 },
  { tag: "enterprise", count: 65 },
  { tag: "support", count: 60 },
  { tag: "integration", count: 45 },
  { tag: "onboarding", count: 40 },
  { tag: "upgrade", count: 35 },
  { tag: "installation", count: 30 },
  { tag: "training", count: 25 },
  { tag: "login", count: 20 },
  { tag: "voicemail", count: 15 },
  { tag: "missed", count: 10 },
];

// Helper function to get data for a specific date range
export const getCallStatsByDateRange = (
  startDate: string,
  endDate: string
): DailyCallStats[] => {
  const start = new Date(startDate).getTime();
  const end = new Date(endDate).getTime();

  return DAILY_CALL_STATS.filter((stat) => {
    const statDate = new Date(stat.date).getTime();
    return statDate >= start && statDate <= end;
  });
};

// Helper function to calculate summary statistics
export const calculateSummaryStats = (stats: DailyCallStats[]) => {
  if (stats.length === 0) return null;

  const totalCalls = stats.reduce((sum, day) => sum + day.totalCalls, 0);
  const completedCalls = stats.reduce(
    (sum, day) => sum + day.completedCalls,
    0
  );
  const missedCalls = stats.reduce((sum, day) => sum + day.missedCalls, 0);
  const voicemails = stats.reduce((sum, day) => sum + day.voicemails, 0);
  const totalDuration = stats.reduce(
    (sum, day) => sum + day.averageDuration * day.completedCalls,
    0
  );
  const averageDuration =
    completedCalls > 0 ? totalDuration / completedCalls : 0;
  const conversionRate =
    stats.reduce((sum, day) => sum + day.conversionRate, 0) / stats.length;

  return {
    totalCalls,
    completedCalls,
    missedCalls,
    voicemails,
    averageDuration,
    conversionRate,
  };
};
