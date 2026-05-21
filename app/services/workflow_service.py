import json

from app.models import WorkflowRule
from app.services.communication_service import send_low_stock_alert


def _value_from_context(context, field_name):
    value = context
    for part in field_name.split("."):
        value = getattr(value, part, value.get(part) if isinstance(value, dict) else None)
        if value is None:
            break
    return value


def _condition_matches(condition, context):
    left = _value_from_context(context, condition.field_name)
    right = condition.value
    if condition.operator == "lt":
        return float(left or 0) < float(right or 0)
    if condition.operator == "gt":
        return float(left or 0) > float(right or 0)
    if condition.operator == "contains":
        return str(right or "") in str(left or "")
    if condition.operator == "not_equals":
        return str(left or "") != str(right or "")
    return str(left or "") == str(right or "")


def run_workflows(trigger_event, context):
    executed = []
    rules = WorkflowRule.query.filter_by(trigger_event=trigger_event, is_active=True).all()
    for rule in rules:
        if any(not _condition_matches(condition, context) for condition in rule.conditions):
            continue
        for action in rule.actions:
            config = json.loads(action.config_json or "{}")
            if action.action_type == "send_low_stock_alert" and config.get("product"):
                send_low_stock_alert(config["product"])
            executed.append({"rule": rule.name, "action": action.action_type})
    return executed
