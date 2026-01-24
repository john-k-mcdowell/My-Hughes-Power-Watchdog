# Monitoring Switch Implementation Plan

## Problem
The monitoring switch exists but doesn't fully work:
- `async_turn_off()` calls `async_disconnect()` which cancels background tasks ✓
- `async_turn_on()` only sets update_interval but does NOT restart background tasks ✗

When the switch is turned back ON, the command worker and health monitor tasks remain cancelled.

## Solution

### Changes Required

#### 1. coordinator.py - Add `start_monitoring()` method
Add a public method to restart background tasks:

```python
def start_monitoring(self) -> None:
    """Start/restart monitoring and background tasks."""
    self._start_background_tasks()
```

#### 2. switch.py - Update `async_turn_on()`
Call the new method when turning on:

```python
async def async_turn_on(self, **kwargs: Any) -> None:
    """Turn the switch on - enable monitoring."""
    from datetime import timedelta
    from .const import DEFAULT_SCAN_INTERVAL

    # Resume coordinator updates
    self.coordinator.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    # Restart background tasks
    self.coordinator.start_monitoring()

    await self.coordinator.async_refresh()
    self.async_write_ha_state()
    _LOGGER.debug("Monitoring enabled for %s", self.coordinator.address)
```

### Files to Modify
1. `coordinator.py` - Add 1 method (3 lines)
2. `switch.py` - Add 1 line to `async_turn_on()`

### Version
- Bump to v0.3.3 (patch release - bug fix)

## Todo Items
- [ ] Add `start_monitoring()` method to coordinator.py
- [ ] Update `async_turn_on()` in switch.py to call `start_monitoring()`
- [ ] Update version to 0.3.3
- [ ] Verify syntax
- [ ] Commit, push, and create release
