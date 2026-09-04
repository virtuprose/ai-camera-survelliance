export type ConnectionState = "online" | "degraded" | "offline" | "connecting";
export type CameraSwitchState = "idle" | "switching" | "failed";
export type AutomaticMonitoringState = "active" | "warming_up" | "attention" | "unavailable";
export type SourceMode = "real" | "simulated";
export type EventStatus = "new" | "acknowledged" | "dismissed";
export type Severity = "info" | "warning" | "critical";
export type PpeAssessmentState = "not_visible" | "checking" | "detected" | "missing" | "unavailable";

export interface PpeItemAssessment {
  state: PpeAssessmentState;
  confidence: number | null;
  visibilityConfidence: number;
  blueRatio: number | null;
  colourProfile?: "blue" | "red";
  colourRatio?: number | null;
  threshold: number;
  stableForMs: number;
  side: "left" | "right" | null;
  roi: [number, number, number, number] | null;
  required?: boolean;
  verificationMethod?: string;
  centreRatio?: number | null;
  componentRatio?: number | null;
  horizontalSpanRatio?: number | null;
  verticalSpanRatio?: number | null;
  centreOffsetRatio?: number | null;
  qualityScore?: number | null;
  decisionReason?: string | null;
}

export interface PpeReadiness {
  brightness: number;
  lightingReady: boolean;
  faceVisible: boolean;
  leftHandVisible: boolean;
  rightHandVisible: boolean;
  torsoVisible: boolean;
  framingReady: boolean;
  guidance: string[];
}

export interface PpeStatus {
  mask: boolean | null;
  gloves: boolean | null;
  hairnet: boolean | null;
  apron: boolean | null;
  confidence: number | null;
  assessmentAvailable?: boolean;
  items?: Record<string, PpeItemAssessment>;
  readiness?: PpeReadiness;
}

export interface ActiveEmployee {
  employeeId: string | null;
  displayName: string;
  photoUrl?: string | null;
  badgeMarkerId?: number | null;
  identityMethod?: "aruco_badge";
  trackId: number | null;
  zone: string;
  activity: string;
  enteredAt: string | null;
  timeInZoneSeconds: number;
  badgeConfidence: number | null;
  personConfidence?: number | null;
  ppe: PpeStatus;
}

export interface DetectionIssue {
  code: string;
  title: string;
  detail: string;
}

export interface DetectionState {
  status: "idle" | "attention" | "observing" | "compliant";
  trackId: number | null;
  identityDetected: boolean;
  identityStatus: {
    state: "associated" | "not_associated";
    label: string;
    detail: string;
  };
  ppeDetected: boolean;
  issues: DetectionIssue[];
  ppeItems: Record<string, PpeItemAssessment>;
  readiness: PpeReadiness | null;
  proof: {
    zone: string;
    activity: string;
    personConfidence: number | null;
    ppeConfidence: number | null;
    movementSamples: number;
    evidencePolicy: "snapshot_and_clip_on_persistent_event";
    brightness: number | null;
    framingReady: boolean;
    assessmentAvailable: boolean;
  } | null;
  resetGeneration: number;
  lastResetAt: string | null;
  updatedAt: string | null;
}

export interface ProcessState {
  id: string | null;
  label: string;
  status: "idle" | "running" | "complete" | "exception";
  startedAt: string | null;
  elapsedSeconds: number;
  targetMinSeconds: number;
  targetMaxSeconds: number;
}

export interface TemperatureState {
  sensorId: string;
  label: string;
  valueC: number;
  minC: number;
  maxC: number;
  status: "safe" | "warning" | "critical";
  sourceMode: SourceMode;
  sampledAt: string;
}

export interface InventoryItem {
  sku: string;
  label: string;
  quantity: number;
  unit: string;
}

export interface DemoEvent {
  id: string;
  deviceId: string;
  trackId: number | null;
  occurredAt: string;
  type: string;
  title: string;
  detail: string;
  severity: Severity;
  sourceMode: SourceMode;
  status: EventStatus;
  employeeId: string | null;
  employeeName: string | null;
  zone: string | null;
  confidence: number | null;
  evidenceUrl: string | null;
  retentionUntil: string;
  metadata?: Record<string, unknown>;
}

export interface DeviceHealth {
  edge: ConnectionState;
  camera: ConnectionState;
  cloud: ConnectionState;
  livekit: ConnectionState;
  stream: ConnectionState;
  sensor: ConnectionState;
  storage: ConnectionState;
  storageError: string | null;
  cameraId: string;
  cameraLabel: string;
  cameraSwitchState: CameraSwitchState;
  cameraSwitchMessage: string | null;
  sourceType: "avfoundation" | "rtsp" | "file";
  modelLabel: string;
  processedFps: number;
  automaticMonitoring: AutomaticMonitoringState;
  monitoringMessage: string;
  ppeVerifier?: {
    status: "passed" | "failed";
    automaticSelfTest: boolean;
    failures: string[];
  };
  temperatureSource?: {
    kind: "simulated" | "serial" | "mqtt";
    sourceMode: SourceMode;
    error: string | null;
  };
  queueDepth: number;
  lastFrameAt: string | null;
  updatedAt: string;
}

export interface CameraOption {
  id: string;
  label: string;
  description: string;
  kind: "avfoundation" | "rtsp" | "file";
  source: string | number | null;
  registered: boolean;
  active: boolean;
}

export interface CameraCatalog {
  activeId: string;
  options: CameraOption[];
  switchState: CameraSwitchState;
  message: string | null;
}

export interface LiveState {
  health: DeviceHealth;
  activeEmployee: ActiveEmployee | null;
  detection: DetectionState;
  process: ProcessState;
  temperature: TemperatureState;
  inventory: InventoryItem[];
  recentEvents: DemoEvent[];
}

export type WorkspaceMode = "live" | "simulated" | "planned";
export type DemoPersona = "executive" | "qa_supervisor" | "operations" | "it";
export type IncidentPriority = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "open" | "investigating" | "action_required" | "resolved" | "closed";

export interface EnterpriseSite {
  id: string;
  code: string;
  name: string;
  timezone: string;
  mode: WorkspaceMode;
}

export interface EnterpriseWorkspace {
  id: string;
  siteId: string;
  code: string;
  name: string;
  departmentType: string;
  mode: WorkspaceMode;
  deviceCode: string | null;
}

export interface EnterpriseContext {
  organization: { id: string; name: string };
  sites: EnterpriseSite[];
  workspaces: EnterpriseWorkspace[];
  activeShift: { id: string; name: string; startsAt: string; endsAt: string };
  personas: DemoPersona[];
  updatedAt: string;
}

export interface IncidentActivity {
  id: string;
  actor: string;
  action: string;
  detail: string;
  createdAt: string;
}

export interface EnterpriseIncident {
  id: string;
  sourceEventId: string;
  siteId: string;
  workspaceId: string;
  shiftId: string;
  title: string;
  detail: string;
  priority: IncidentPriority;
  status: IncidentStatus;
  sourceMode: SourceMode;
  owner: string | null;
  dueAt: string;
  rootCause: string | null;
  correctiveAction: string | null;
  resolutionNote: string | null;
  resolutionType: string | null;
  createdAt: string;
  updatedAt: string;
  retentionUntil: string;
  version: number;
  evidenceUrl: string | null;
  employeeName: string | null;
  zone: string | null;
  confidence: number | null;
  activity?: IncidentActivity[];
}

export interface OverviewMetrics {
  openCriticalIncidents: number;
  ppeCompliance: number | null;
  ppeDeterminateChecks: number;
  processOnTime: number | null;
  completedProcesses: number;
  activeTemperatureExcursions: number;
  systemAvailability: number;
}

export interface EnterpriseOverview {
  metrics: OverviewMetrics;
  priorityIncidents: EnterpriseIncident[];
  siteHealth: Array<{ siteId: string; name: string; mode: WorkspaceMode; status: string; openIncidents: number }>;
  updatedAt: string;
}

export interface SopStage {
  id: string;
  sequence: number;
  name: string;
  trigger: string;
  targetMinSeconds: number;
  targetMaxSeconds: number;
}

export interface SopTemplate {
  id: string;
  code: string;
  name: string;
  version: string;
  sourceMode: SourceMode;
  siteId: string;
  workspaceId: string;
  stages: SopStage[];
}

export interface EnterpriseProcessRun {
  id: string;
  sopId: string;
  label: string;
  status: "running" | "complete" | "exception";
  startedAt: string;
  completedAt: string | null;
  elapsedSeconds: number | null;
  targetMinSeconds: number;
  targetMaxSeconds: number;
  sourceMode: SourceMode;
  siteId: string;
  workspaceId: string;
  shiftId: string;
}

export interface OracleReadiness {
  status: "not_connected";
  sourceMode: "simulated";
  message: string;
  mappings: Array<{ source: string; target: string; status: "proposed" }>;
  samplePayload: Record<string, unknown>;
  externalRequestsEnabled: false;
}
