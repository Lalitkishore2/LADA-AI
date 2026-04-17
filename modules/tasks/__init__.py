"""
LADA Unified Task Registry

Central registry for all LADA tasks with:
- Durable persistence (survives restart)
- Multiple execution models (parallel, sequential, DAG)
- Step-level progress tracking
- Resume token support
- Full audit history
"""

from modules.tasks.task_registry import (
    RegistryTask,
    TaskStep,
    TaskStatus,
    TaskPriority,
    StepStatus,
    StepResult,
    StepType,
    TaskRegistry,
    get_registry,
)

from modules.tasks.task_flow_registry import (
    TaskFlow,
    FlowStatus,
    FlowStepConfig,
    FlowTemplate,
    ExecutionMode,
    TaskFlowRegistry,
    get_flow_registry,
)

from modules.tasks.task_maintenance import (
    TaskMaintenance,
    MaintenanceStats,
    HealthStatus,
    get_maintenance,
    startup_tasks,
)

from modules.tasks.task_integration import (
    OrchestratorAdapter,
    AutomationAdapter,
    PipelineAdapter,
    get_orchestrator_adapter,
    get_automation_adapter,
    get_pipeline_adapter,
)

from modules.tasks.task_notifications import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_KILLED,
    create_task_notification_xml,
    parse_task_notification_xml,
)

__all__ = [
    # Core types
    'RegistryTask',
    'TaskStep',
    'TaskStatus',
    'TaskPriority',
    'StepStatus',
    'StepResult',
    'StepType',
    # Registry
    'TaskRegistry',
    'get_registry',
    # Flow types
    'TaskFlow',
    'FlowStatus',
    'FlowStepConfig',
    'FlowTemplate',
    'ExecutionMode',
    'TaskFlowRegistry',
    'get_flow_registry',
    # Maintenance
    'TaskMaintenance',
    'MaintenanceStats',
    'HealthStatus',
    'get_maintenance',
    'startup_tasks',
    # Integration adapters
    'OrchestratorAdapter',
    'AutomationAdapter',
    'PipelineAdapter',
    'get_orchestrator_adapter',
    'get_automation_adapter',
    'get_pipeline_adapter',
    # Task notifications
    'STATUS_COMPLETED',
    'STATUS_FAILED',
    'STATUS_KILLED',
    'create_task_notification_xml',
    'parse_task_notification_xml',
]
