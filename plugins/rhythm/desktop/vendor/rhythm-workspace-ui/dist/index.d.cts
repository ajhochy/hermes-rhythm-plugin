import * as react from 'react';
import { ReactNode, FormEvent, Ref } from 'react';
import * as Icons from 'lucide-react';
import { LucideProps } from 'lucide-react';

/** A gateway rejects with this — never a raw HTTP status or a transport-specific error class —
 * so a screen can drive its loading/empty/error/forbidden/readonly state machine without
 * knowing anything about REST, GraphQL, or IPC. */
type RhythmGatewayErrorKind = 'forbidden' | 'not_found' | 'unavailable' | 'server_error' | 'conflict' | 'uncertain';
declare class RhythmGatewayError extends Error {
    readonly kind: RhythmGatewayErrorKind;
    constructor(kind: RhythmGatewayErrorKind, message: string);
}
interface RhythmWorkspaceMember {
    id: string;
    name: string;
    initials: string;
}
type TaskStatus = 'open' | 'in_progress' | 'waiting_for_reply' | 'done';
type TaskBucket = 'past-due' | 'today' | 'week' | 'month' | 'no-due' | 'completed';
type TaskEnergy = '' | '🔥' | '⚡' | '🌱';
type PreferredAgent = '' | 'claude-code' | 'codex';
interface RhythmTaskCollaborator {
    id: string;
    name: string;
    initials: string;
}
interface RhythmTask {
    id: string;
    title: string;
    notes: string;
    status: TaskStatus;
    bucket: TaskBucket;
    priority: 0 | 1 | 2 | 3;
    tags: string[];
    scheduledDate?: string;
    dueDate?: string;
    createdAt: string;
    createdBy: string;
    ownerId: string;
    /** True when this task belongs to someone else and the current user is only a collaborator —
     * gates delete/collaborator-management actions to the owner (task-owner-only permission). */
    isShared: boolean;
    /** A non-manual source (a synchronized rhythm/project/automation/calendar event) is
     * inspect-only here; edits belong in that source of truth. */
    sourceType: 'manual' | 'rhythm' | 'project' | 'automation' | 'calendar_shadow_event' | 'prod_mirror';
    sourceName?: string;
    preferredAgent: PreferredAgent;
    energy: TaskEnergy;
    collaborators: RhythmTaskCollaborator[];
}
type CreateRhythmTaskInput = Pick<RhythmTask, 'title'> & Partial<Pick<RhythmTask, 'notes' | 'scheduledDate' | 'dueDate' | 'preferredAgent' | 'collaborators'>>;
type UpdateRhythmTaskInput = Partial<Pick<RhythmTask, 'title' | 'notes' | 'scheduledDate' | 'dueDate' | 'preferredAgent' | 'energy' | 'status'>>;
interface TasksGateway {
    list(): Promise<RhythmTask[]>;
    members(): Promise<RhythmWorkspaceMember[]>;
    create(input: CreateRhythmTaskInput): Promise<RhythmTask>;
    update(id: string, input: UpdateRhythmTaskInput): Promise<RhythmTask>;
    delete(id: string): Promise<void>;
    addCollaborator(id: string, memberId: string): Promise<RhythmTask>;
    removeCollaborator(id: string, memberId: string): Promise<RhythmTask>;
    /** Narrow semantic operations for constrained hosts.  A host which exposes these must
     * canonical-read-back before resolving successfully. */
    complete?(id: string, generation?: string): Promise<RhythmTask>;
    reschedule?(id: string, scheduledDate: string, generation?: string): Promise<RhythmTask>;
}
interface RhythmDashboardTask {
    id: string;
    title: string;
    notes: string;
    status: 'open' | 'done';
    bucket: 'past-due' | 'today' | 'week' | 'unscheduled';
    scheduledDate?: string;
    dueDate?: string;
    dueLabel: string;
    collaboratorId?: string;
    collaboratorName?: string;
}
interface RhythmDashboardProjectStep {
    id: string;
    title: string;
    notes: string;
    status: 'open' | 'done';
    dueLabel: string;
}
interface RhythmDashboardProject {
    id: string;
    title: string;
    owner: string;
    dueLabel: string;
    steps: RhythmDashboardProjectStep[];
}
interface RhythmDashboardThreadPreview {
    id: string;
    title: string;
    preview: string;
    senderName?: string;
    unreadCount: number;
}
interface RhythmDashboardSummary {
    openTaskCount: number;
    threadCount: number;
    tasks: RhythmDashboardTask[];
    project: RhythmDashboardProject | null;
    unreadThreads: RhythmDashboardThreadPreview[];
}
type CreateDashboardTaskInput = Pick<RhythmDashboardTask, 'title'> & Partial<Pick<RhythmDashboardTask, 'notes' | 'scheduledDate' | 'dueDate' | 'collaboratorId'>>;
type UpdateDashboardTaskInput = Partial<Pick<RhythmDashboardTask, 'title' | 'notes' | 'scheduledDate' | 'dueDate' | 'status'>> & {
    collaboratorId?: string | null;
};
interface DashboardGateway {
    summary(): Promise<RhythmDashboardSummary>;
    members(): Promise<RhythmWorkspaceMember[]>;
    createTask(input: CreateDashboardTaskInput): Promise<RhythmDashboardTask>;
    updateTask(id: string, input: UpdateDashboardTaskInput): Promise<RhythmDashboardTask>;
    updateProjectStep(id: string, input: Partial<Pick<RhythmDashboardProjectStep, 'title' | 'status'>>): Promise<RhythmDashboardProjectStep>;
}
interface RhythmPlannerTask {
    id: string;
    source: 'task' | 'project-step';
    /** Durable source-owned identity for a project-instance step. This is deliberately distinct
     * from the planner row id: project-step mutations must never be sent through task routes. */
    projectStepId?: string;
    title: string;
    notes: string;
    status: 'open' | 'done';
    scheduledDate?: string;
    dueDate?: string;
    scheduledOrder: number;
    energy?: TaskEnergy;
    projectName?: string;
    collaborators: RhythmTaskCollaborator[];
    /** A project-step-sourced entry is rendered with source context. Its controls require both
     * host write capability and a durable projectStepId. */
    readonly: boolean;
}
interface RhythmPlannerEvent {
    id: string;
    title: string;
    date: string;
    timeLabel: string;
    notes: string;
    allDay: boolean;
}
interface RhythmPlannerDay {
    date: string;
    label: string;
    tasks: RhythmPlannerTask[];
    events: RhythmPlannerEvent[];
}
interface RhythmPlannerWeek {
    weekLabel: string;
    weekStart: string;
    days: RhythmPlannerDay[];
    backlog: RhythmPlannerTask[];
}
interface PlannerGateway {
    week(weekLabel: string): Promise<RhythmPlannerWeek>;
    members(): Promise<RhythmWorkspaceMember[]>;
    scheduleTask(id: string, input: {
        scheduledDate?: string;
    }): Promise<RhythmPlannerTask>;
    updateProjectStep(id: string, input: Partial<Pick<RhythmPlannerTask, 'notes' | 'dueDate' | 'status'>>): Promise<RhythmPlannerTask>;
    scheduleProjectStep(id: string, input: {
        dueDate?: string;
    }): Promise<RhythmPlannerTask>;
    create(input: Pick<RhythmPlannerTask, 'title'> & Partial<Pick<RhythmPlannerTask, 'notes' | 'scheduledDate' | 'dueDate' | 'energy'>>): Promise<RhythmPlannerTask>;
    update(id: string, input: Partial<Pick<RhythmPlannerTask, 'title' | 'notes' | 'scheduledDate' | 'dueDate' | 'energy' | 'status'>>): Promise<RhythmPlannerTask>;
    addCollaborator(id: string, memberId: string): Promise<RhythmPlannerTask>;
    removeCollaborator(id: string, memberId: string): Promise<RhythmPlannerTask>;
}
type ProjectInstanceStatus = 'planning' | 'active' | 'on_hold' | 'complete';
interface RhythmProjectStep {
    id: string;
    title: string;
    notes: string;
    status: 'open' | 'done';
    dueDate?: string;
    scheduledDate?: string;
    assigneeId?: string;
    milestoneId?: string | null;
}
interface RhythmProjectMilestone {
    id: string;
    title: string;
    sortOrder: number;
}
interface RhythmProjectTemplateStep {
    id: string;
    title: string;
    offsetDays: number;
    offsetDescription: string;
    assigneeId?: string;
}
interface RhythmProjectTemplate {
    id: string;
    name: string;
    description: string;
    anchorType: string;
    steps: RhythmProjectTemplateStep[];
}
interface RhythmProject {
    id: string;
    templateId: string;
    name: string;
    anchorDate: string;
    status: ProjectInstanceStatus;
    ownerId: string;
    collaborators: RhythmWorkspaceMember[];
    milestones: RhythmProjectMilestone[];
    steps: RhythmProjectStep[];
}
interface ProjectsGateway {
    templates(): Promise<RhythmProjectTemplate[]>;
    list(): Promise<RhythmProject[]>;
    members(): Promise<RhythmWorkspaceMember[]>;
    generate(templateId: string, input: {
        anchorDate: string;
        name?: string;
    }): Promise<RhythmProject>;
    createTemplate(input: Pick<RhythmProjectTemplate, 'name' | 'description' | 'anchorType'>): Promise<RhythmProjectTemplate>;
    updateTemplate(id: string, input: Partial<Pick<RhythmProjectTemplate, 'name' | 'description' | 'anchorType'>>): Promise<RhythmProjectTemplate>;
    deleteTemplate(id: string): Promise<void>;
    addTemplateStep(templateId: string, input: Omit<RhythmProjectTemplateStep, 'id'> & {
        templateId: string;
    }): Promise<RhythmProjectTemplateStep>;
    updateTemplateStep(templateId: string, stepId: string, input: Partial<Omit<RhythmProjectTemplateStep, 'id'>> & {
        templateId: string;
    }): Promise<RhythmProjectTemplateStep>;
    deleteTemplateStep(templateId: string, stepId: string): Promise<void>;
    delete(id: string): Promise<void>;
    updateStep(instanceId: string, stepId: string, input: Partial<Pick<RhythmProjectStep, 'title' | 'notes' | 'status' | 'dueDate' | 'scheduledDate' | 'assigneeId' | 'milestoneId'>> & {
        instanceId: string;
    }): Promise<RhythmProjectStep>;
    addMilestone(instanceId: string, input: Pick<RhythmProjectMilestone, 'title'>): Promise<RhythmProjectMilestone>;
    addCollaborator(instanceId: string, memberId: string): Promise<RhythmProject>;
    removeCollaborator(instanceId: string, memberId: string): Promise<RhythmProject>;
}
type RhythmCadence = 'weekly' | 'monthly' | 'annual';
interface RhythmStep {
    id: string;
    title: string;
    assigneeId?: string | null;
}
interface RhythmRhythm {
    id: string;
    title: string;
    frequency: RhythmCadence;
    dayOfWeek: number;
    dayOfMonth: number;
    month: number;
    sequential: boolean;
    enabled: boolean;
    ownerId: string;
    ownerName: string;
    collaborators: RhythmWorkspaceMember[];
    steps: RhythmStep[];
    generatedCount: number;
    completedCount: number;
    remainingCount: number;
    waitingOn: string | null;
    nextDueDate: string | null;
    completionRatio: number;
    createdAt: string;
}
type RhythmStepDraft = Pick<RhythmStep, 'title'> & {
    assigneeId?: string | null;
};
type CreateRhythmRhythmInput = Pick<RhythmRhythm, 'title' | 'frequency'> & Partial<Pick<RhythmRhythm, 'dayOfWeek' | 'dayOfMonth' | 'month' | 'sequential' | 'enabled'>> & {
    steps?: RhythmStepDraft[];
};
interface RhythmsGateway {
    list(): Promise<RhythmRhythm[]>;
    members(): Promise<RhythmWorkspaceMember[]>;
    create(input: CreateRhythmRhythmInput): Promise<RhythmRhythm>;
    update(id: string, input: Partial<Pick<RhythmRhythm, 'title' | 'enabled' | 'sequential' | 'frequency' | 'dayOfWeek' | 'dayOfMonth' | 'month'>>): Promise<RhythmRhythm>;
    delete(id: string): Promise<void>;
    addStep(id: string, input: RhythmStepDraft): Promise<RhythmStep>;
    /** Replace is intentional: production persists the complete ordered workflow on edit. */
    replaceSteps(id: string, steps: RhythmStepDraft[]): Promise<RhythmRhythm>;
    addCollaborator(id: string, memberId: string): Promise<RhythmRhythm>;
    removeCollaborator(id: string, memberId: string): Promise<RhythmRhythm>;
}
type MessageThreadType = 'direct' | 'group';
interface RhythmMessage {
    id: string;
    senderId: string;
    senderName: string;
    body: string;
    createdAt: string;
}
interface RhythmMessageThread {
    id: string;
    title: string;
    type: MessageThreadType;
    participants: RhythmWorkspaceMember[];
    messages: RhythmMessage[];
    lastMessage: string;
    updatedAt: string;
    unreadCount: number;
}
interface MessagesGateway {
    list(): Promise<RhythmMessageThread[]>;
    members(): Promise<RhythmWorkspaceMember[]>;
    createThread(input: {
        participantIds: string[];
        type: MessageThreadType;
        title?: string;
    }): Promise<RhythmMessageThread>;
    send(threadId: string, body: string): Promise<RhythmMessage>;
    markRead(threadId: string): Promise<void>;
    markUnread(threadId: string): Promise<void>;
    renameThread(threadId: string, title: string): Promise<RhythmMessageThread>;
    deleteThread(threadId: string): Promise<void>;
}
interface RhythmFacility {
    id: string;
    name: string;
    building: string | null;
    description: string;
}
interface RhythmReservation {
    id: string;
    facilityId: string;
    title: string;
    requesterName: string;
    creatorId: string;
    start: string;
    end: string;
    notes: string | null;
    seriesId?: string;
    groupId?: string;
    external?: boolean;
    conflicted?: boolean;
    automation?: boolean;
}
type CreateReservationInput = Pick<RhythmReservation, 'facilityId' | 'title' | 'start' | 'end'> & Partial<Pick<RhythmReservation, 'notes' | 'requesterName'>>;
type UpdateReservationInput = Partial<Pick<RhythmReservation, 'title' | 'requesterName' | 'start' | 'end' | 'notes'>>;
type CreateFacilityInput = Pick<RhythmFacility, 'name'> & Partial<Pick<RhythmFacility, 'building' | 'description'>>;
type UpdateFacilityInput = Partial<Pick<RhythmFacility, 'name' | 'building' | 'description'>>;
interface FacilitiesGateway {
    facilities(): Promise<RhythmFacility[]>;
    createFacility(input: CreateFacilityInput): Promise<RhythmFacility>;
    updateFacility(id: string, input: UpdateFacilityInput): Promise<RhythmFacility>;
    deleteFacility(id: string): Promise<void>;
    reservations(range: {
        start: string;
        end: string;
    }): Promise<RhythmReservation[]>;
    createReservation(input: CreateReservationInput): Promise<RhythmReservation>;
    updateReservation(id: string, input: UpdateReservationInput): Promise<RhythmReservation>;
    deleteReservation(id: string): Promise<void>;
    updateGroup(groupId: string, input: UpdateReservationInput): Promise<RhythmReservation[]>;
    deleteGroup(groupId: string): Promise<{
        deletedCount: number;
    }>;
    deleteSeries(seriesId: string): Promise<{
        deletedCount: number;
    }>;
    /** Preferred atomic server operation for a recurrence/automation cleanup. */
    deleteReservations?(ids: string[]): Promise<{
        deletedIds: string[];
    }>;
}
type IntegrationProviderId = 'google-calendar' | 'gmail' | 'planning-center';
type IntegrationAccountStatus = 'connected' | 'disconnected' | 'needs_reauth' | 'error';
interface RhythmIntegrationAccount {
    id: IntegrationProviderId;
    name: string;
    monogram: string;
    status: IntegrationAccountStatus;
    identity?: string;
    lastSyncedAt?: string;
    errorMessage?: string;
}
interface RhythmCalendarSource {
    id: string;
    name: string;
    description: string;
    primary?: boolean;
    selected: boolean;
}
interface RhythmGmailSignal {
    id: string;
    threadId: string;
    subject?: string;
    sender?: string;
    snippet?: string;
    unread: boolean;
}
interface IntegrationsGateway {
    accounts(): Promise<RhythmIntegrationAccount[]>;
    calendarSources(): Promise<RhythmCalendarSource[]>;
    saveCalendarSelection(selectedIds: string[]): Promise<RhythmCalendarSource[]>;
    gmailSignals(): Promise<RhythmGmailSignal[]>;
    sync(id: IntegrationProviderId): Promise<RhythmIntegrationAccount>;
    disconnect(id: IntegrationProviderId): Promise<RhythmIntegrationAccount>;
    /** Beginning an OAuth/authorization flow is a host+backend concern (it needs a real
     * redirect URL and a live credential) — this package only asks the host to do it. */
    requestAuthorization(id: IntegrationProviderId): void;
}
type AutomationSource = 'rhythm' | 'planning_center' | 'google_calendar' | 'gmail';
type AutomationActionType = 'create_task' | 'create_project_from_template' | 'tag_task' | 'send_notification' | 'auto_schedule' | 'create_reservation';
interface AutomationCondition {
    field: string;
    operator: 'equals' | 'not_equals' | 'contains' | 'not_contains';
    value: string;
}
interface RhythmAutomation {
    id: string;
    name: string;
    source: AutomationSource;
    accountLabel: string;
    triggerKey: string;
    triggerLabel: string;
    actionType: AutomationActionType;
    actionLabel: string;
    enabled: boolean;
    createdAt: string;
    lastMatchedAt: string | null;
    matchCountLastRun: number;
    previewSummary: string;
    conditions: AutomationCondition[];
    /** Provider-owned values such as templates or a selected room. */
    actionConfig?: Record<string, string>;
    /** A host account identifier; only meaningful for external providers. */
    sourceAccountId?: string | null;
}
type CreateAutomationInput = Pick<RhythmAutomation, 'name' | 'source' | 'triggerKey' | 'triggerLabel' | 'actionType' | 'actionLabel'> & Partial<Pick<RhythmAutomation, 'conditions' | 'enabled' | 'actionConfig' | 'sourceAccountId'>>;
interface AutomationsGateway {
    list(): Promise<RhythmAutomation[]>;
    create(input: CreateAutomationInput): Promise<RhythmAutomation>;
    update(id: string, input: Partial<Pick<RhythmAutomation, 'name' | 'source' | 'triggerKey' | 'triggerLabel' | 'actionType' | 'actionLabel' | 'enabled' | 'conditions' | 'actionConfig' | 'sourceAccountId'>>): Promise<RhythmAutomation>;
    delete(id: string): Promise<void>;
    /** Optional live catalog/detail ports. Hosts that do not provide them retain the list view. */
    catalog?(): Promise<AutomationCatalog>;
    preview?(id: string): Promise<AutomationPreview>;
    resync?(id: string): Promise<RhythmAutomation>;
}
interface AutomationCatalog {
    providers: Array<{
        source: AutomationSource;
        status: 'connected' | 'stale' | 'disconnected';
        accountId?: string;
        accountLabel?: string;
    }>;
    triggers: Partial<Record<AutomationSource, Array<{
        key: string;
        label: string;
    }>>>;
    actions: Array<{
        type: AutomationActionType;
        label: string;
        configFields?: Array<{
            key: string;
            label: string;
        }>;
    }>;
}
interface AutomationPreview {
    summary: string;
    matchedAt: string | null;
    matchCount: number;
}
interface RhythmDomainGateway {
    dashboard: DashboardGateway;
    tasks: TasksGateway;
    planner: PlannerGateway;
    projects: ProjectsGateway;
    rhythms: RhythmsGateway;
    messages: MessagesGateway;
    facilities: FacilitiesGateway;
    integrations: IntegrationsGateway;
    automations: AutomationsGateway;
}

type RhythmThemeMode = 'light' | 'dark';
/** Semantic design tokens the host already owns (mirrors Hermes/Rhythm's existing CSS custom
 * property vocabulary: bg/surface/fg/border/accent/radii) so a host maps its own tokens once,
 * not per-screen. */
interface RhythmHostTokens {
    mode: RhythmThemeMode;
    bg: string;
    surface: string;
    surfaceWarm: string;
    surfaceRaised: string;
    fg: string;
    fgSecondary: string;
    fgMuted: string;
    border: string;
    borderSoft: string;
    accent: string;
    accentOn: string;
    accentHover: string;
    success: string;
    warning: string;
    danger: string;
    info: string;
    fontUi: string;
    fontMono: string;
    radiusSm: string;
    radiusMd: string;
    radiusLg: string;
    radiusPill: string;
    focusRing: string;
    shadow: string;
}
type RhythmViewport = 'compact' | 'regular' | 'expanded';
interface RhythmCurrentUser {
    /** Stable host identity used only for local owner/capability decisions; never a credential. */
    id?: string;
    displayName: string;
    initials: string;
    /** Collaboration surfaces are writable only when this is explicitly set to write; omission is inspect-only. */
    collaborationCapability?: 'read' | 'write';
    /** Host-neutral, affirmative capabilities. An absent list is intentionally read-only. */
    capabilities?: readonly RhythmWorkspaceCapability[];
}
type RhythmWorkspaceCapability = 'facilities.manage' | 'facilities.reserve' | 'facilities.create-facility' | 'facilities.update-facility' | 'facilities.delete-facility' | 'facilities.create-reservation' | 'facilities.update-reservation' | 'facilities.delete-reservation' | 'facilities.update-group' | 'facilities.delete-group' | 'facilities.delete-series' | 'facilities.delete-reservations' | 'automations.write' | 'integrations.write' | 'dashboard.write' | 'tasks.write'
/** Narrow task mutation grants for hosts such as Hermes.  They deliberately do not
 * imply create/delete/edit/collaboration access. */
 | 'tasks.complete' | 'tasks.reschedule'
/** Broad legacy Planner access is an explicit capability, never inferred from
 * collaborationCapability. M5 constrained hosts use the semantic grants below. */
 | 'planner.write'
/** M5 is intentionally semantic: constrained hosts never receive the broad
 * planner/projects/rhythms write ports. */
 | 'planner.schedule-task' | 'planner.update-task' | 'planner.update-project-step' | 'planner.schedule-project-step'
/** Broad legacy Rhythms access remains explicit for general hosts. */
 | 'rhythms.write' | 'rhythms.create-rule' | 'rhythms.update-rule' | 'rhythms.delete-rule' | 'rhythms.create-step' | 'rhythms.update-step' | 'rhythms.delete-step' | 'rhythms.reorder-step'
/** Broad legacy Projects access remains explicit for general hosts. */
 | 'projects.write' | 'projects.create-template' | 'projects.update-template' | 'projects.delete-template' | 'projects.create-instance' | 'projects.update-instance' | 'projects.delete-instance' | 'projects.create-step' | 'projects.update-step' | 'projects.update-template-step' | 'projects.delete-step' | 'projects.reorder-step' | 'projects.create-milestone' | 'projects.update-milestone' | 'projects.delete-milestone';
interface RhythmTaskOperationConfirmation {
    taskId: string;
    generation: string;
    operation: 'complete' | 'reschedule';
    /** ISO date for rescheduling; omitted for completion. */
    scheduledDate?: string;
}
/** A host-issued, foreground-only confirmation for an exact M5 operation.
 * `payload` must be canonical JSON (no credentials, URLs, actor, workspace or
 * profile fields); the host binds those server-side before issuing its one-use
 * receipt.  This is deliberately a semantic action, not a generic HTTP port. */
interface RhythmWorkspaceOperationConfirmation {
    operation: Exclude<RhythmWorkspaceCapability, 'facilities.manage' | 'facilities.reserve' | 'automations.write' | 'integrations.write' | 'dashboard.write' | 'tasks.write'>;
    entityId: string;
    payload: Record<string, string | number | boolean | null | string[] | Array<Record<string, string | null>>>;
    generation: string;
}
/** The ten non-agent screens this package exposes — used only for host-owned, in-package
 * cross-screen navigation (e.g. Dashboard's "Open planner" shortcut). Never includes an
 * agent surface: this package has no notion of one. */
type RhythmScreenId = 'dashboard' | 'tasks' | 'planner' | 'projects' | 'rhythms' | 'messages' | 'facilities' | 'integrations' | 'automations' | 'artifacts';
interface RhythmHostAdapter {
    tokens: RhythmHostTokens;
    viewport: RhythmViewport;
    currentUser: RhythmCurrentUser;
    /** Optional: a screen asks the host to switch to a sibling screen (e.g. Dashboard's "Open
     * planner"). The host owns routing between screens; this package does not. */
    onNavigateToScreen?: (screenId: RhythmScreenId, context?: {
        relatedId?: string;
    }) => void;
    /** Optional: called when a screen wants to hand off to a follow-up outside this package —
     * a quick action ("help me finish this"), an OAuth/authorization redirect (Integrations),
     * or any other action this package must not perform itself (creating an agent session,
     * navigating to an agent surface, building an authorization URL). Intentionally untyped
     * beyond a label + context id — this package must never call an agent-session API, build a
     * bearer/OAuth URL, or know what the host does with the request. */
    onRequestFollowUp?: (context: {
        screen: string;
        label: string;
        action?: string;
        relatedId?: string;
    }) => void;
    /** A foreground-only host port.  The screen calls this only after its focus-trapped
     * confirmation dialog; the host rejects stale, mismatched, or reused payloads. */
    confirmTaskOperation?: (confirmation: RhythmTaskOperationConfirmation) => Promise<boolean>;
    confirmWorkspaceOperation?: (confirmation: RhythmWorkspaceOperationConfirmation) => Promise<boolean>;
}

interface RhythmWorkspaceProviderProps {
    gateway: RhythmDomainGateway;
    host: RhythmHostAdapter;
    children: ReactNode;
}
/** The single composition root a host mounts once. It owns no React runtime of its own —
 * `react`/`react-dom` are peer dependencies (see package.json) — so nesting this inside a
 * host's existing tree never creates a second React instance. */
declare function RhythmWorkspaceProvider({ gateway, host, children }: RhythmWorkspaceProviderProps): react.JSX.Element;
declare function useRhythmDomainGateway(): RhythmDomainGateway;
declare function useRhythmHost(): RhythmHostAdapter;

/** Every scoped root element carries exactly this class; src/styles/rhythm.css scopes all
 * selectors under it so the package never leaks unprefixed global rules into a host page. */
declare const RHYTHM_ROOT_CLASS = "rhythm-workspace-root";
declare const defaultRhythmTokens: RhythmHostTokens;
/** Maps a host's design tokens onto this package's own `--rhythm-*` CSS variable
 * vocabulary, applied as an inline style on the scoped root. Never reads or writes an
 * unprefixed/global custom property (e.g. `--bg`, `--fg`) — a host may have its own,
 * unrelated variables under those names, and colliding with them was the reason M1 exists. */
declare function mapHostTokens(tokens: Partial<RhythmHostTokens> | undefined): Record<string, string>;

type RhythmArtifactKind = 'document' | 'image' | 'other';
interface RhythmArtifact {
    id: string;
    title: string;
    kind: RhythmArtifactKind;
}
interface ArtifactsGateway {
    list(): Promise<RhythmArtifact[]>;
}
/** A host-sanitized, immutable artifact bundle.  This package never receives a
 * URL, credential, filesystem path, or transport handle. */
interface ArtifactHostDocument {
    artifactId: string;
    sessionId: string;
    bundleGeneration: string;
    stateGeneration: string;
    bodyHtml: string;
    styleText: string;
    scriptText: string;
    capabilities: readonly ArtifactHostCapability[];
}
/** The renderer may request only these named, host-mediated operations. */
type ArtifactHostCapability = 'state.get' | 'state.update' | 'pco.services.read';
interface ArtifactHostCapabilityMessage {
    type: 'rhythm-artifact-capability';
    requestId: string;
    frameId: string;
    artifactId: string;
    sessionId: string;
    bundleGeneration: string;
    stateGeneration: string;
    capability: ArtifactHostCapability;
    payload: unknown;
}
/** `conflict` is deliberately relayed unchanged so existing independent bundle
 * and state optimistic-concurrency behavior stays owned by the host. */
interface ArtifactHostCapabilityResult {
    status: 'ok' | 'conflict' | 'rejected' | 'error';
    payload?: unknown;
    bundleGeneration?: string;
    stateGeneration?: string;
}
/** Explicit opt-in bridge.  Opening supplies an already-sanitized document and
 * receiving a message is the only way an artifact can request host authority. */
interface ArtifactHostPort {
    open(artifactId: string): Promise<ArtifactHostDocument>;
    receive(message: ArtifactHostCapabilityMessage): Promise<ArtifactHostCapabilityResult>;
}

interface ArtifactsScreenProps {
    /** Deliberately optional and separate from RhythmDomainGateway — a host must pass this
     * explicitly to unlock the screen. See src/artifacts/types.ts. */
    artifactsGateway?: ArtifactsGateway;
    /** Kept separate from list access: an artifact gets no renderer bridge until
     * its host explicitly supplies this capability port. */
    artifactHostPort?: ArtifactHostPort;
}
declare function ArtifactsScreen({ artifactsGateway, artifactHostPort }: ArtifactsScreenProps): react.JSX.Element;

declare function AutomationsScreen(): react.JSX.Element;

declare function DashboardScreen(): react.JSX.Element;

declare function FacilitiesScreen(): react.JSX.Element;

declare function IntegrationsScreen(): react.JSX.Element;

declare function MessagesScreen(): react.JSX.Element;

declare function PlannerScreen(): react.JSX.Element;

declare function ProjectsScreen(): react.JSX.Element;

declare function RhythmsScreen(): react.JSX.Element;

declare function TasksScreen(): react.JSX.Element;

type IconName = keyof typeof iconSet;
declare const iconSet: {
    activity: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    archive: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    attach: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    bell: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    book: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    calendar: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    check: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    chevronDown: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    chevronRight: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    close: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    copy: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    delete: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    download: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    filter: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    history: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    link: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    mail: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    menu: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    more: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    plus: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    refresh: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    rename: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    search: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    settings: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    sliders: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    sparkles: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    upload: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    users: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
    warning: react.ForwardRefExoticComponent<Omit<Icons.LucideProps, "ref"> & react.RefAttributes<SVGSVGElement>>;
};
declare function Icon({ name, size, ...props }: {
    name: IconName;
} & LucideProps): react.JSX.Element;

declare function FocusDialog({ open, title, description, onClose, children, testId, wide, }: {
    open: boolean;
    title: string;
    description?: string;
    onClose(): void;
    children: ReactNode;
    testId: string;
    wide?: boolean;
}): react.JSX.Element | null;

declare function HeaderTaskAction({ onClick, disabled, describedBy, testId, label, }: {
    onClick(): void;
    disabled?: boolean;
    describedBy?: string;
    testId: string;
    label?: string;
}): react.JSX.Element;

type TaskCreateMember = {
    id: string;
    name: string;
};
type TaskCreateTestIds = {
    title: string;
    notes: string;
    scheduledDate: string;
    dueDate: string;
    collaborator: string;
    cancel: string;
    submit: string;
    error?: string;
    mutations?: string;
};
type TaskCreateFormProps = {
    idPrefix: string;
    onSubmit(event: FormEvent<HTMLFormElement>): void;
    onCancel(): void;
    members: readonly TaskCreateMember[];
    testIds: TaskCreateTestIds;
    titleRef?: Ref<HTMLInputElement>;
    titleError?: string;
    onTitleChange?(): void;
    defaultScheduledDate?: string;
    disabled?: boolean;
    describedBy?: string;
    noValidate?: boolean;
};
declare function TaskCreateForm({ idPrefix, onSubmit, onCancel, members, testIds, titleRef, titleError, onTitleChange, defaultScheduledDate, disabled, describedBy, noValidate, }: TaskCreateFormProps): react.JSX.Element;

type QuickActionPresetId = 'help-finish' | 'draft-next-steps' | 'summarize' | 'follow-up-tasks';
interface QuickActionPreset {
    id: QuickActionPresetId;
    label: string;
}
declare const quickActionPresets: QuickActionPreset[];

export { type ArtifactHostCapability, type ArtifactHostCapabilityMessage, type ArtifactHostCapabilityResult, type ArtifactHostDocument, type ArtifactHostPort, type ArtifactsGateway, ArtifactsScreen, type ArtifactsScreenProps, type AutomationActionType, type AutomationCondition, type AutomationSource, type AutomationsGateway, AutomationsScreen, type CreateAutomationInput, type CreateDashboardTaskInput, type CreateFacilityInput, type CreateReservationInput, type CreateRhythmRhythmInput, type CreateRhythmTaskInput, type DashboardGateway, DashboardScreen, type FacilitiesGateway, FacilitiesScreen, FocusDialog, HeaderTaskAction, Icon, type IconName, type IntegrationAccountStatus, type IntegrationProviderId, type IntegrationsGateway, IntegrationsScreen, type MessageThreadType, type MessagesGateway, MessagesScreen, type PlannerGateway, PlannerScreen, type PreferredAgent, type ProjectInstanceStatus, type ProjectsGateway, ProjectsScreen, type QuickActionPreset, type QuickActionPresetId, RHYTHM_ROOT_CLASS, type RhythmArtifact, type RhythmArtifactKind, type RhythmAutomation, type RhythmCadence, type RhythmCalendarSource, type RhythmCurrentUser, type RhythmDashboardProject, type RhythmDashboardProjectStep, type RhythmDashboardSummary, type RhythmDashboardTask, type RhythmDashboardThreadPreview, type RhythmDomainGateway, type RhythmFacility, RhythmGatewayError, type RhythmGatewayErrorKind, type RhythmGmailSignal, type RhythmHostAdapter, type RhythmHostTokens, type RhythmIntegrationAccount, type RhythmMessage, type RhythmMessageThread, type RhythmPlannerDay, type RhythmPlannerEvent, type RhythmPlannerTask, type RhythmPlannerWeek, type RhythmProject, type RhythmProjectMilestone, type RhythmProjectStep, type RhythmProjectTemplate, type RhythmProjectTemplateStep, type RhythmReservation, type RhythmRhythm, type RhythmScreenId, type RhythmStep, type RhythmTask, type RhythmTaskCollaborator, type RhythmTaskOperationConfirmation, type RhythmThemeMode, type RhythmViewport, type RhythmWorkspaceMember, type RhythmWorkspaceOperationConfirmation, RhythmWorkspaceProvider, type RhythmWorkspaceProviderProps, type RhythmsGateway, RhythmsScreen, type TaskBucket, TaskCreateForm, type TaskCreateMember, type TaskEnergy, type TaskStatus, type TasksGateway, TasksScreen, type UpdateDashboardTaskInput, type UpdateFacilityInput, type UpdateRhythmTaskInput, defaultRhythmTokens, mapHostTokens, quickActionPresets, useRhythmDomainGateway, useRhythmHost };
