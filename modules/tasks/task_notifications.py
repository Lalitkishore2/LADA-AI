"""
Task lifecycle notification helpers.

Provides OpenClaw-compatible XML notification formatting for completed,
failed, and cancelled task events.
"""

from typing import Any, Dict, Optional
import xml.etree.ElementTree as ET


STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_KILLED = "killed"
ALLOWED_STATUSES = {STATUS_COMPLETED, STATUS_FAILED, STATUS_KILLED}


def create_task_notification_xml(
    task_id: str,
    status: str,
    summary: str,
    result: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a task-notification XML string."""
    normalized_status = (status or "").strip().lower()
    if normalized_status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported task notification status: {status}")

    root = ET.Element("task-notification")

    task_id_elem = ET.SubElement(root, "task-id")
    task_id_elem.text = task_id

    status_elem = ET.SubElement(root, "status")
    status_elem.text = normalized_status

    summary_elem = ET.SubElement(root, "summary")
    summary_elem.text = summary

    if result:
        result_elem = ET.SubElement(root, "result")
        result_elem.text = result

    if usage:
        usage_elem = ET.SubElement(root, "usage")

        total_tokens_elem = ET.SubElement(usage_elem, "total_tokens")
        total_tokens_elem.text = str(int(usage.get("total_tokens", 0) or 0))

        tool_uses_elem = ET.SubElement(usage_elem, "tool_uses")
        tool_uses_elem.text = str(int(usage.get("tool_uses", 0) or 0))

        duration_elem = ET.SubElement(usage_elem, "duration_ms")
        duration_elem.text = str(int(usage.get("duration_ms", 0) or 0))

    return ET.tostring(root, encoding="unicode")


def parse_task_notification_xml(xml_payload: str) -> Dict[str, Any]:
    """Parse task notification XML into dict."""
    root = ET.fromstring(xml_payload)
    usage_node = root.find("usage")
    usage = None
    if usage_node is not None:
        usage = {
            "total_tokens": int(usage_node.findtext("total_tokens") or 0),
            "tool_uses": int(usage_node.findtext("tool_uses") or 0),
            "duration_ms": int(usage_node.findtext("duration_ms") or 0),
        }

    return {
        "task_id": root.findtext("task-id"),
        "status": root.findtext("status"),
        "summary": root.findtext("summary"),
        "result": root.findtext("result"),
        "usage": usage,
    }
