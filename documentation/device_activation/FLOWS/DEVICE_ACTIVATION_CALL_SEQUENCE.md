# Device Activation - Call Sequence Diagrams

**Date:** 2025-12-24
**BusinessCaseID:** BC-DA-006 (Call Frequency & Sequencing Logic)
**Purpose:** Visual documentation of Device Activation call timing, frequency, and sequencing patterns

---

## Table of Contents

1. [Diagram 1: Calls 1-4 Timeline](#diagram-1-calls-1-4-timeline)
2. [Diagram 2: Call 5+ Timeline (90-Day Window)](#diagram-2-call-5-timeline-90-day-window)
3. [Diagram 3: Callback Timeline](#diagram-3-callback-timeline)

---

## Overview

Device Activation uses two distinct call frequency patterns based on attempt number:

- **Calls 1-4 (Initial Phase):** Frequent attempts using BUSINESS days (2 days for Calls 2-3, 5 days for Call 4) with a maximum of 4 attempts. **No 90-day limit.**
- **Calls 5+ (Extended Phase):** After 7 days (>7 CALENDAR days = 8+ days frequency, calls only on business days) within a 90-day window starting from Call 5 creation.

Additionally, the system supports callback scheduling when members request to be called back at a specific time.

---

## Diagram 1: Calls 1-4 Timeline

### Purpose
Shows the timing and frequency of the first 4 call attempts, including the activation_start_date calculation and BUSINESS day spacing between attempts (excludes weekends and US federal holidays).

### Mermaid Diagram

```mermaid
gantt
    title Device Activation Calls 1-4 Timeline (Business Days)
    dateFormat YYYY-MM-DD
    axisFormat %m/%d

    section Delivery & Activation
    Device Delivery           :milestone, m1, 2025-01-01, 0d
    activation_start_date (delivery + 2 biz days) :milestone, m2, 2025-01-03, 0d

    section Call Attempts (BUSINESS day frequency, max 4)
    Call 1 Eligible          :c1, 2025-01-03, 1d
    Call 1 Made              :milestone, c1done, 2025-01-03, 0d

    Call 2 Eligible (2 biz days later) :c2, 2025-01-07, 1d
    Call 2 Made              :milestone, c2done, 2025-01-07, 0d

    Call 3 Eligible (2 biz days later) :c3, 2025-01-09, 1d
    Call 3 Made              :milestone, c3done, 2025-01-09, 0d

    Call 4 Eligible (5 biz days later) :c4, 2025-01-16, 1d
    Call 4 Made              :milestone, c4done, 2025-01-16, 0d

    section Transition to Call 5+
    Move to Weekly Frequency :milestone, m3, 2025-01-16, 0d
```

### ASCII Diagram

```
Mon Jan 1:      📦 Device Delivery
                    ↓
                    (2 business days: Tue Jan 2, Wed Jan 3)
                    ↓
Wed Jan 3:      ✅ activation_start_date = Jan 3
                📞 Call 1 Eligible & Made
                    ↓
                    (2 BUSINESS days: Thu Jan 4, Fri Jan 5)
                    Skip Sat Jan 6, Sun Jan 7 (weekend)
                    ↓
Mon Jan 7:      📞 Call 2 Eligible & Made
                    ↓
                    (2 BUSINESS days: Tue Jan 8, Wed Jan 9)
                    ↓
Wed Jan 9:      📞 Call 3 Eligible & Made
                    ↓
                    (5 BUSINESS days: Thu Jan 10, Fri Jan 11, Mon Jan 14, Tue Jan 15, Wed Jan 16)
                    Skip Sat Jan 12, Sun Jan 13 (weekend)
                    ↓
Wed Jan 16:     📞 Call 4 Eligible & Made
                    ↓
                    ⚠️ Transition to Call 5+ (7 CALENDAR days, 90-day window)

Timeline Rules (Calls 1-4):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Frequency: BUSINESS days (Monday-Friday, NO weekends/holidays)
  - Calls 2-3: Minimum 2 business days between attempts
  - Call 4: Minimum 5 business days after Call 3
• Max Attempts: 4 total (hard limit)
• No 90-Day Limit: Calls 1-4 can span any duration
• activation_start_date: delivery_date + 2 business days
• Business Days: Excludes weekends and US federal holidays
• Uses Python get_business_days_between() function (af_code/shared/business_hours_utils.py)
• Business day filtering happens in Python AFTER SQL query (eligibility_service.py:666-730)
• Eligibility: Checked every 15 minutes by scheduler
```

### Key Points

1. **activation_start_date Calculation:**
   - Formula: `delivery_date + 2 business days`
   - Business days exclude weekends and company holidays
   - Example: Delivery on Friday Jan 1 → activation_start_date = Tuesday Jan 5 (skips weekend)
   - Code: `af_code/af_device_activation_logic.py` (Phase 4 - Transform)

2. **Call 1 Eligibility:**
   - Eligible on activation_start_date (first day device can be activated)
   - No previous attempts required
   - Checked every 15 minutes by timer trigger
   - Code: `af_code/device_activation_scheduler/services/eligibility_service.py:91-97`

3. **Calls 2-4 Frequency:**
   - **Calls 2-3:** Minimum 2 BUSINESS days after previous attempt
   - **Call 4:** Minimum 5 BUSINESS days after Call 3
   - Business days = Monday-Friday, excluding US federal holidays
   - ⚠️ **Business day filtering happens in PYTHON** (NOT SQL)
   - Python: Uses `get_business_days_between()` function (af_code/shared/business_hours_utils.py)
   - Filtering logic: `eligibility_service.py:666-730`
   - Maximum 4 total attempts (hard limit enforced by eligibility query)
   - Code: `af_code/device_activation_scheduler/services/eligibility_service.py:98-109`

4. **No 90-Day Limit for Calls 1-4:**
   - Unlike Calls 5+, the initial 4 attempts have NO campaign end date restriction
   - Members can receive Calls 1-4 regardless of how much time has passed since delivery
   - Only frequency rule applies (business day minimum spacing)

5. **Transition to Call 5+:**
   - After Call 4 completes, system switches to weekly frequency (7 CALENDAR days spacing)
   - IMPORTANT: Call 5+ frequency uses 7 CALENDAR days (includes weekends/holidays in the count)
   - IMPORTANT: Call 5+ calls are ONLY made on business days (weekends/holidays are skipped)
   - **Defense in Depth:** Business day validation happens in TWO places:
     1. Eligibility filter explicitly checks `is_business_day(now_utc)` for Call 5+ members
     2. Business hours filter validates via `can_make_call()` (implicit business day check)
   - 90-day window logic activates starting from Call 5 creation
   - Code: `af_code/device_activation_scheduler/services/batch_orchestrator.py:_update_call_5_enrollments()`
   - Code: `af_code/device_activation_scheduler/services/eligibility_service.py:680-695` (Call 5+ business day filter)

### Related Code Files

- **Eligibility Query:** `af_code/device_activation_scheduler/services/eligibility_service.py:42-240`
- **activation_start_date Calculation:** `af_code/af_device_activation_logic.py` (Phase 4 - Transform, MERGE enrollments)
- **Business Day Utility:** `af_code/shared/business_hours_utils.py`

---

## Diagram 2: Call 5+ Timeline (90-Day Window)

### Purpose
Shows the weekly call frequency and 90-day window for Call 5 and beyond, including how call_5_timestamp triggers the campaign end date calculation.

### Mermaid Diagram

```mermaid
gantt
    title Device Activation Call 5+ Timeline (90-Day Window)
    dateFormat YYYY-MM-DD
    axisFormat %m/%d

    section Call 5 Triggers 90-Day Window
    Call 5 Made              :milestone, c5, 2025-01-13, 0d
    call_5_timestamp Set     :milestone, ts, 2025-01-13, 0d
    campaign_end_date = ts + 90 days :milestone, end, 2025-04-13, 0d

    section Weekly Calls (7-day frequency)
    Call 6 Eligible (7d later) :c6, 2025-01-20, 1d
    Call 7 Eligible (7d later) :c7, 2025-01-27, 1d
    Call 8 Eligible (7d later) :c8, 2025-02-03, 1d
    Call N (continues weekly) :cn, 2025-02-10, 60d

    section Campaign End
    90-Day Window Expires    :milestone, expire, 2025-04-13, 0d
    No More Calls After This :crit, nomore, 2025-04-13, 1d
```

### ASCII Diagram

```
Day X (Jan 13):     📞 Call 5 Made
                    ⏰ call_5_timestamp SET (Jan 13 09:30:00-05:00)
                    📅 campaign_end_date = call_5_timestamp + 90 days = Apr 13
                        ↓
                        (7 calendar days)
                        ↓
Day X+7 (Jan 20):   📞 Call 6 Eligible & Made
                        ↓
                        (7 calendar days)
                        ↓
Day X+14 (Jan 27):  📞 Call 7 Eligible & Made
                        ↓
                        (7 calendar days)
                        ↓
Day X+21 (Feb 3):   📞 Call 8 Eligible & Made
                        ↓
                        ... (continue weekly - 7 day spacing) ...
                        ↓
                        ... Call 9 (Feb 10) ...
                        ... Call 10 (Feb 17) ...
                        ... Call 11 (Feb 24) ...
                        ... Call 12 (Mar 3) ...
                        ... [up to ~13 total calls within 90 days] ...
                        ↓
Day X+90 (Apr 13):  🛑 Campaign Ends (campaign_end_date reached)
                    ❌ No more calls eligible
                    📊 Enrollment status may update to 'COMPLETED'

Timeline Rules (Call 5+):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Frequency: Minimum 7 calendar days between attempts (counts weekends/holidays)
• Call Timing: Calls ONLY on business days (Mon-Fri, excluding federal holidays)
• Max Attempts: Unlimited (within 90-day window)
• Window Start: call_5_timestamp (NOT activation_start_date)
• Window Duration: Exactly 90 calendar days
• Window End: call_5_timestamp + 90 days = campaign_end_date
• Eligibility: SYSDATETIMEOFFSET() < campaign_end_date
• Max Possible Calls in Window: ~13 calls (90 days ÷ 7 days)
```

### Key Points

1. **call_5_timestamp Creation:**
   - Set when Call 5 batch is created (Phase 3 of batch orchestration)
   - Stored in `member_campaign_enrollments_enhanced.call_5_timestamp`
   - SQL: `UPDATE ... SET call_5_timestamp = SYSDATETIMEOFFSET() WHERE enrollment_id = ... AND attempt_number = 5`
   - Code: `af_code/device_activation_scheduler/services/batch_orchestrator.py:_update_call_5_enrollments()`

2. **90-Day Window Calculation:**
   - **CRITICAL:** Window starts from `call_5_timestamp`, NOT from `activation_start_date`
   - Formula: `campaign_end_date = call_5_timestamp + 90 days`
   - Example: Call 5 on Jan 13 → campaign_end_date = Apr 13
   - Window is 90 **calendar days** (includes weekends/holidays)

3. **After 7 Days Frequency (8+ Day Spacing):**
   - **Frequency Window:** More than 7 calendar days between attempts (>7 = 8+ days, counts weekends/holidays)
   - **Call Timing:** Calls ONLY made on business days (Mon-Fri, excluding federal holidays)
   - **SQL Frequency Check:** `DATEDIFF(DAY, last_attempt_ts, SYSDATETIMEOFFSET()) > 7`
   - **Python Business Day Check:** `is_business_day(now_utc)` filters out weekends/holidays
   - Call 6 eligible >7 days after Call 5, Call 7 eligible >7 days after Call 6, etc.
   - Code: `af_code/device_activation_scheduler/services/eligibility_service.py:110-132, 680-695`

4. **Unlimited Attempts Within Window:**
   - No maximum attempt count for Call 5+ (unlike Calls 1-4)
   - Theoretical maximum: ~13 calls (90 days ÷ 7 days ≈ 12.86)
   - Actual count varies based on when calls are made and business hours availability

5. **Campaign End Date Enforcement:**
   - Eligibility query checks: `SYSDATETIMEOFFSET() < campaign_end_date`
   - Once current date reaches campaign_end_date, no more calls eligible
   - Member may transition to 'COMPLETED' status (if device not activated)
   - Code: `af_code/device_activation_scheduler/services/eligibility_service.py:123-127`

6. **Why Window Starts from call_5_timestamp:**
   - Allows flexibility in initial 4 attempts (no time pressure)
   - 90-day limit only applies to extended outreach phase
   - Prevents indefinite calling while still allowing reasonable follow-up duration
   - Business rationale: After 4 attempts + 90 days of weekly calls, member likely won't activate

### Example Timeline Calculation

```
Scenario: Member receives device on Jan 1 (Wednesday)

Jan 1:  Device delivery (Wednesday)
Jan 3:  Call 1 (Friday - activation_start_date = delivery + 2 biz days)
Jan 7:  Call 2 (Tuesday - 2 BUSINESS days later: Mon, Tue)
Jan 9:  Call 3 (Thursday - 2 BUSINESS days later: Wed, Thu)
Jan 16: Call 4 (Thursday - 5 BUSINESS days later: Fri, Mon, Tue, Wed, Thu)
Jan 23: Call 5 (Thursday - 7 CALENDAR days later) → call_5_timestamp = Jan 23, campaign_end_date = Apr 23
Jan 20: Call 6 (7d later)
Jan 27: Call 7 (7d later)
Feb 3:  Call 8 (7d later)
Feb 10: Call 9 (7d later)
Feb 17: Call 10 (7d later)
Feb 24: Call 11 (7d later)
Mar 3:  Call 12 (7d later)
Mar 10: Call 13 (7d later)
Mar 17: Call 14 (7d later)
Mar 24: Call 15 (7d later)
Mar 31: Call 16 (7d later)
Apr 7:  Call 17 (7d later)
Apr 13: Campaign ends (90-day window expires)
Apr 14: No longer eligible (SYSDATETIMEOFFSET() >= campaign_end_date)

Total Calls: 17 (4 initial + 13 weekly)
Total Duration: 103 days (Jan 1 to Apr 13)
```

### Related Code Files

- **Call 5 Timestamp Update:** `af_code/device_activation_scheduler/services/batch_orchestrator.py:_update_call_5_enrollments()`
- **90-Day Window Check:** `af_code/device_activation_scheduler/services/eligibility_service.py:123-127`
- **Weekly Frequency Logic:** `af_code/device_activation_scheduler/services/eligibility_service.py:110-132`

---

## Diagram 3: Callback Timeline

### Purpose
Shows the lifecycle of a callback request from creation to execution, including business hours validation, rescheduling logic, and timeout handling.

### Mermaid Diagram

```mermaid
gantt
    title Callback Request Timeline
    dateFormat YYYY-MM-DD HH:mm
    axisFormat %H:%M

    section Member Request
    Call Made - Member Requests Callback :milestone, call, 2025-01-15 14:00, 0h
    Callback Created (scheduled_callback_time = 16:00) :milestone, created, 2025-01-15 14:00, 0h

    section Processing Loop (Every 15 min)
    Scheduler Check 14:15    :s1, 2025-01-15 14:15, 15min
    Scheduler Check 14:30    :s2, 2025-01-15 14:30, 15min
    Scheduler Check 14:45    :s3, 2025-01-15 14:45, 15min
    Scheduler Check 15:00    :s4, 2025-01-15 15:00, 15min
    Scheduler Check 15:15    :s5, 2025-01-15 15:15, 15min
    Scheduler Check 15:30    :s6, 2025-01-15 15:30, 15min
    Scheduler Check 15:45    :s7, 2025-01-15 15:45, 15min
    Scheduler Check 16:00    :s8, 2025-01-15 16:00, 15min

    section Callback Execution
    scheduled_callback_time Reached :milestone, ready, 2025-01-15 16:00, 0h
    Business Hours Check     :bh, 2025-01-15 16:00, 1min
    Callback Made            :milestone, made, 2025-01-15 16:01, 0h
```

### ASCII Diagram

```
2:00 PM:  📞 Original Call - Member says "call me back in 2 hours"
          ✅ Webhook creates callback record
          📝 INSERT into outreach_callback_queue:
              - enrollment_id: abc-123-def
              - scheduled_callback_time: 4:00 PM (16:00)
              - status: 'Pending'
              - attempt_count: 0
              - created_at: 2:00 PM
             ↓
2:15 PM:  ⏰ Scheduler checks (every 15 min) → Too early (skip)
2:30 PM:  ⏰ Scheduler checks → Too early (skip)
2:45 PM:  ⏰ Scheduler checks → Too early (skip)
3:00 PM:  ⏰ Scheduler checks → Too early (skip)
3:15 PM:  ⏰ Scheduler checks → Too early (skip)
3:30 PM:  ⏰ Scheduler checks → Too early (skip)
3:45 PM:  ⏰ Scheduler checks → Too early (skip)
             ↓
4:00 PM:  ✅ scheduled_callback_time REACHED
          ✅ Business hours check:
              - Campaign: operating_hours 9 AM - 5 PM EST
              - Current time: 4:00 PM EST ✓ (within hours)
              - Member timezone: Central (3:00 PM) ✓ (within hours)
          📞 Callback submitted to BatchOrchestrator
          📝 UPDATE outreach_callback_queue:
              - status: 'Completed'
              - attempt_count: 1
              - completed_at: 4:00 PM
          📞 Call made via Bland AI

Callback Flow Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Created: Webhook processes CALL_BACK_SCHEDULED disposition
• Scheduled: scheduled_callback_time set to member's requested time
• Polled: Checked every 15 minutes by timer trigger
• Validated: Business hours check (dual-timezone)
• Executed: Submitted to BatchOrchestrator when time reached
• Completed: Status updated to 'Completed'

Alternative Scenarios:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scenario A: Callback Time AFTER Operating Hours
───────────────────────────────────────────────
4:00 PM:  ❌ scheduled_callback_time reached BUT operating_end_time = 3:00 PM
          ⚠️ Business hours check FAILS (4 PM > 3 PM)
          🔄 Reschedule to next business day at 9:00 AM (operating_start_time)
          📝 UPDATE outreach_callback_queue:
              - scheduled_callback_time: Tomorrow 9:00 AM
              - attempt_count: 1 (incremented)
              - status: 'Pending' (remains pending)

Next Day:
9:00 AM:  ✅ Rescheduled time reached
          ✅ Business hours check PASSES
          📞 Callback submitted


Scenario B: 24-Hour Timeout
─────────────────────────
2:00 PM (Day 1):  📞 Callback created
3:00 PM (Day 1):  ❌ Business hours violation → Reschedule to next day 9 AM
9:00 AM (Day 2):  ❌ Business hours violation → Reschedule to next day 9 AM
9:00 AM (Day 3):  ❌ Business hours violation → Reschedule to next day 9 AM
                  ⏰ Check timeout: created_at + 24h = 2:00 PM (Day 2)
                  🚨 Timeout condition met: DATEDIFF(HOUR, created_at, NOW()) >= 24
                  📝 UPDATE outreach_callback_queue:
                      - status: 'Timeout'
                  ❌ Callback removed from queue (no more attempts)


Scenario C: 3-Attempt Timeout
───────────────────────────
2:00 PM:  📞 Callback created
4:00 PM:  ❌ Business hours violation → Reschedule (attempt_count = 1)
Next Day 9 AM: ❌ Business hours violation → Reschedule (attempt_count = 2)
Next Day 9 AM: ❌ Business hours violation → Reschedule (attempt_count = 3)
              🚨 Timeout condition met: attempt_count >= 3
              📝 UPDATE outreach_callback_queue:
                  - status: 'Timeout'
              ❌ Callback removed from queue (no more attempts)
```

### Key Points

1. **Callback Creation (Webhook Processing):**
   - Triggered by Bland AI disposition: `CALL_BACK_SCHEDULED`
   - Webhook extracts requested callback time from Bland AI response
   - INSERT into `outreach_callback_queue` with status='Pending'
   - Code: `af_code/bland_ai_webhook/services/database_orchestrator.py:_build_insert_callback_queue()`

2. **Callback Polling (Every 15 Minutes):**
   - Timer trigger runs `device_activation_scheduler` every 15 minutes
   - CallbackScheduler.get_pending_callbacks() retrieves callbacks where:
     - `status = 'Pending'`
     - `scheduled_callback_time <= SYSDATETIMEOFFSET()`
     - Timeout not reached (24h OR 3 attempts)
   - Code: `af_code/device_activation_scheduler/services/callback_scheduler.py:get_pending_callbacks()`

3. **Business Hours Validation (Dual-Timezone):**
   - **Campaign Operating Hours:** 9 AM - 5 PM in campaign's `operating_tz` (e.g., EST)
   - **Member Operating Hours:** 9 AM - 5 PM in member's `timezone` (e.g., Central)
   - **Both must be satisfied** (AND condition, not OR)
   - If either fails → Reschedule to next business day at `operating_start_time`
   - Code: `af_code/device_activation_scheduler/services/callback_scheduler.py:_validate_callback_business_hours()`

4. **Rescheduling Logic:**
   - When business hours check fails:
     1. Calculate next business day (skip weekends/holidays)
     2. Set `scheduled_callback_time = next_business_day + operating_start_time` (e.g., 9:00 AM)
     3. Increment `attempt_count`
     4. Keep status as 'Pending'
   - Code: `af_code/device_activation_scheduler/services/callback_scheduler.py:_reschedule_callback()`

5. **Timeout Conditions (OR Logic):**
   - **24-Hour Timeout:** `DATEDIFF(HOUR, created_at, SYSDATETIMEOFFSET()) >= 24`
   - **3-Attempt Timeout:** `attempt_count >= 3`
   - **Either condition triggers timeout** (OR logic, not AND)
   - When timeout occurs:
     - Update status to 'Timeout'
     - Remove from pending queue
     - No further callback attempts
   - Code: `af_code/device_activation_scheduler/services/callback_scheduler.py:_handle_callback_timeouts()`

6. **Callback Execution:**
   - When time reached AND business hours validated:
     1. Fetch callback details (enrollment_id, member_id, etc.)
     2. Submit to BatchOrchestrator as single-member batch
     3. Update callback status to 'Completed'
     4. Normal 3-phase batch tracking applies (batch → attempts → vendor_id)
   - Code: `af_code/device_activation_scheduler/services/callback_scheduler.py:process_callbacks()`

7. **Callback Priority:**
   - Callbacks processed BEFORE regular call eligibility
   - Eligibility query excludes members with pending callbacks
   - Ensures callback is honored instead of regular call
   - Code: `af_code/device_activation_scheduler/services/eligibility_service.py:87-91`

### Example Callback Scenarios

**Scenario 1: Successful Same-Day Callback**
```
2:00 PM: Member requests callback in 2 hours
2:00 PM: Callback created (scheduled for 4:00 PM)
4:00 PM: Time reached, business hours valid → Call made ✅
```

**Scenario 2: Callback After Hours → Reschedule**
```
6:00 PM: Member requests callback in 1 hour (scheduled for 7:00 PM)
7:00 PM: Time reached, but operating_end_time = 5:00 PM → Reschedule ⚠️
Next Day 9:00 AM: Rescheduled time, business hours valid → Call made ✅
```

**Scenario 3: Multiple Reschedules → 3-Attempt Timeout**
```
Day 1, 4:00 PM: Callback created, scheduled for 6:00 PM (after hours)
Day 1, 6:00 PM: Reschedule to Day 2, 9:00 AM (attempt_count = 1)
Day 2, 9:00 AM: Business hours fail (member timezone issue), reschedule (attempt_count = 2)
Day 3, 9:00 AM: Business hours fail again, reschedule (attempt_count = 3)
Day 4, 9:00 AM: attempt_count >= 3 → Timeout ❌
```

**Scenario 4: 24-Hour Timeout**
```
Monday 4:00 PM: Callback created
Monday 6:00 PM: Reschedule to Tuesday 9:00 AM (attempt_count = 1)
Tuesday 9:00 AM: Business hours fail, reschedule to Wednesday 9:00 AM (attempt_count = 2)
Tuesday 4:00 PM: 24 hours elapsed since created_at → Timeout ❌
```

### Related Code Files

- **Callback Creation:** `af_code/bland_ai_webhook/services/database_orchestrator.py:_build_insert_callback_queue()`
- **Callback Polling:** `af_code/device_activation_scheduler/services/callback_scheduler.py:get_pending_callbacks()`
- **Business Hours Validation:** `af_code/device_activation_scheduler/services/callback_scheduler.py:_validate_callback_business_hours()`
- **Rescheduling Logic:** `af_code/device_activation_scheduler/services/callback_scheduler.py:_reschedule_callback()`
- **Timeout Handling:** `af_code/device_activation_scheduler/services/callback_scheduler.py:_handle_callback_timeouts()`
- **Callback Execution:** `af_code/device_activation_scheduler/services/callback_scheduler.py:process_callbacks()`

---

## Summary

These three diagrams illustrate the complete call sequencing logic for Device Activation:

1. **Calls 1-4:** Initial rapid outreach (BUSINESS days: 2 days for Calls 2-3, 5 days for Call 4, max 4 attempts, no time limit)
2. **Calls 5+:** Extended weekly outreach (7 CALENDAR days frequency, calls only on business days, unlimited attempts, 90-day window)
3. **Callbacks:** Member-requested callback handling (business hours validation, 24 CALENDAR hour timeout protection)

**Key Architectural Decisions:**

- **Two-Phase Frequency Model:** Rapid initial attempts transition to weekly long-term follow-up
- **90-Day Window Starts at Call 5:** Allows flexibility in initial outreach without indefinite calling
- **Callback Timeout Protection:** Prevents callback queue buildup from business hours mismatches
- **Dual-Timezone Validation:** Respects both MG operating hours and member availability
- **Scheduler Polling:** 15-minute timer provides balance between responsiveness and resource usage

**Related Documentation:**

- [Data Flow Diagrams](DEVICE_ACTIVATION_DATA_FLOW.md) - CSV processing, scheduler flow, webhook processing
- [State Machine Diagrams](DEVICE_ACTIVATION_STATE_MACHINES.md) - Status transitions for enrollments, batches, attempts, callbacks
- [System Architecture](DEVICE_ACTIVATION_SYSTEM_ARCHITECTURE.md) - Component overview, database schema, integration points
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md) - Master reference document

---

**End of Document**
