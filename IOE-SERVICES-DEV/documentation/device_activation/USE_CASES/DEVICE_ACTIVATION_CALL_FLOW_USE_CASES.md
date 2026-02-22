# Device Activation Call Flow - Complete Use Cases

**Document Version:** 1.1
**Last Updated:** 2026-01-17 (Updated for new campaign_end_date logic)
**BusinessCaseID:** BC-DA-001, BC-DA-003, BC-DA-006, BC-DA-007 (Campaign Closure)
**Author:** AI-POD Team - Data Science

**Version 1.1 Changes (2026-01-17):**
- Updated 90-day window to start from activation_start_date (not call_5_timestamp)
- Added BC-DA-007 (Campaign Closure) references
- Updated all use cases to reflect hourly campaign closure scheduler

---

## Table of Contents

1. [Overview](#overview)
2. [Call Sequence Timeline](#call-sequence-timeline)
3. [Business Days vs Calendar Days](#business-days-vs-calendar-days)
4. [Holiday Calculation](#holiday-calculation)
5. [Business Hours Validation](#business-hours-validation)
6. [Use Case 1: Member in EST Timezone](#use-case-1-member-in-est-timezone)
7. [Use Case 2: Member in PST Timezone](#use-case-2-member-in-pst-timezone)
8. [Use Case 3: Calls During Holidays](#use-case-3-calls-during-holidays)
9. [Use Case 4: Weekend Handling](#use-case-4-weekend-handling)
10. [Use Case 5: Multi-Timezone Scenarios](#use-case-5-multi-timezone-scenarios)
11. [Decision Logic Reference](#decision-logic-reference)
12. [Troubleshooting Guide](#troubleshooting-guide)

---

## Overview

This document provides comprehensive use cases for Device Activation campaign call flows. It explains:

- **When** each call happens (Call 1 through Call 15+)
- **How** business days and holidays are calculated
- **What** business hours apply to each timezone
- **Why** certain calls are made or skipped

### Key Principles (UPDATED 2026-01-17)

1. **Call Frequency** = CALENDAR DAYS (includes weekends)
2. **Call Timing** = BUSINESS DAYS ONLY (Mon-Fri, no holidays)
3. **Business Hours** = Dual-timezone validation (MG EST + Member timezone)
4. **90-Day Window** = Starts from activation_start_date (when Call 1 is eligible) - UPDATED 2026-01-17
5. **Campaign Closure** = Hourly scheduler (BC-DA-007) auto-unenrolls expired members

---

## Call Sequence Timeline

### Standard Timeline Example

```
📦 Day 1 (Monday, Jan 1): Device delivered to member
   ↓
📅 Day 3 (Wednesday, Jan 3): CALL 1 - activation_start_date
   ↓ (2 calendar days)
📅 Day 5 (Friday, Jan 5): CALL 2 - Call 1 + 2 days
   ↓ (2 calendar days)
📅 Day 7 (Sunday, Jan 7): Eligible for Call 3 (skipped - weekend)
📅 Day 8 (Monday, Jan 8): CALL 3 MADE
   ↓ (5 calendar days)
📅 Day 12 (Friday, Jan 12): Eligible for Call 4 (skipped - weekend)
📅 Day 15 (Monday, Jan 15): CALL 4 MADE
   ↓ (7 calendar days)
📅 Day 22 (Monday, Jan 22): CALL 5 MADE
   ↓ (7 calendar days, weekly)
📅 Day 29 (Monday, Jan 29): CALL 6 MADE
   ↓ (7 calendar days, weekly)
📅 Day 36 (Monday, Feb 5): CALL 7 MADE
   ↓ (Continue weekly until 90-day window expires...)
📅 Day 90 (April 1): Last calls within 90-day window
   ↓
📅 Day 93 (April 4): ❌ Campaign ends (90 days from activation_start_date = Jan 3)
   ⏰ Hourly campaign closure scheduler unenrolls member
```

### Call Frequency Rules

| Call | Frequency | Calendar Days | Type |
|------|-----------|---------------|------|
| Call 1 | activation_start_date | Delivery + 2 biz days | First attempt |
| Call 2 | Call 1 + 2 days | 2 calendar days | Early attempt |
| Call 3 | Call 2 + 2 days | 2 calendar days | Early attempt |
| Call 4 | Call 3 + 5 days | 5 calendar days | Final early attempt |
| Call 5+ | Previous + 7 days | 7 calendar days (weekly) | Extended attempts |

**Important (UPDATED 2026-01-17):**
- **All calls (1-5+)** are subject to 90-day window from activation_start_date
- campaign_end_date = activation_start_date + 90 days (set at enrollment)
- Hourly campaign closure (BC-DA-007) auto-unenrolls members when campaign_end_date expires

---

## Business Days vs Calendar Days

### Calendar Days (Frequency Calculation)

The SQL eligibility query counts **CALENDAR DAYS**, not business days.

**SQL Logic:**
```sql
-- Call 2-3: 2 CALENDAR days since last attempt
DATEDIFF(day, last_attempt_date, SYSDATETIMEOFFSET()) >= 2

-- Call 4: 5 CALENDAR days since Call 3
DATEDIFF(day, last_attempt_date, SYSDATETIMEOFFSET()) >= 5

-- Call 5+: 7 CALENDAR days since last attempt
DATEDIFF(day, last_attempt_date, SYSDATETIMEOFFSET()) >= 7
```

**Example:**
```
Call 1: Monday, Jan 1
        ↓ (2 calendar days = 48 hours)
Call 2: Wednesday, Jan 3
        ✅ Counts ALL days including weekends!

If Call 1 was Friday, Jan 5:
        ↓ (2 calendar days)
Call 2 eligible: Sunday, Jan 7
        ❌ But Sunday is weekend - actual call made Monday, Jan 8
```

### Business Days (Timing Validation)

After frequency check passes, Python validates **BUSINESS DAYS**.

**Python Logic:**
```python
def is_business_day(check_date: datetime) -> bool:
    # Check 1: Weekend?
    if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check 2: Federal Holiday?
    if check_date.date() in US_HOLIDAYS:
        return False

    # ✅ Business Day!
    return True
```

**Business Days Exclude:**
- ❌ Saturdays (weekday index = 5)
- ❌ Sundays (weekday index = 6)
- ❌ US Federal Holidays

---

## Holiday Calculation

### US Federal Holidays (Auto-Detected)

The system uses Python `holidays` library with `observed=True`:

```python
US_HOLIDAYS = holidays.US(observed=True)
```

### 2025 Federal Holidays

| Date | Day | Holiday |
|------|-----|---------|
| Jan 1, 2025 | Wednesday | New Year's Day |
| Jan 20, 2025 | Monday (3rd) | Martin Luther King Jr. Day |
| Feb 17, 2025 | Monday (3rd) | Presidents' Day |
| May 26, 2025 | Monday (last) | Memorial Day |
| July 4, 2025 | Friday | Independence Day |
| Sep 1, 2025 | Monday (1st) | Labor Day |
| Oct 13, 2025 | Monday (2nd) | Columbus Day |
| Nov 11, 2025 | Tuesday | Veterans Day |
| Nov 27, 2025 | Thursday (4th) | Thanksgiving |
| Dec 25, 2025 | Thursday | Christmas |

### Observed Holidays ("observed=True")

When a holiday falls on a **weekend**, it's observed on the nearest weekday:

**Example 1: Independence Day on Saturday**
```
July 4, 2026 (Saturday) = Independence Day
→ Observed on Friday, July 3, 2026
→ BOTH Friday AND Saturday are non-business days
```

**Example 2: Christmas on Sunday**
```
Dec 25, 2022 (Sunday) = Christmas
→ Observed on Monday, Dec 26, 2022
→ BOTH Sunday AND Monday are non-business days
```

---

## Business Hours Validation

### Dual-Timezone Validation

**ALL calls require BOTH timezones to be within business hours:**

1. **Medical Guardian Hours:** 9:00 AM - 5:00 PM EST (America/New_York)
2. **Member Local Hours:** 9:00 AM - 5:00 PM (member.timezone)

### Validation Logic

```python
def can_make_call(call_time: datetime, member_timezone: pytz.tzinfo) -> Tuple[bool, str]:
    # Check 1: Business day? (Mon-Fri, not holiday)
    if not is_business_day(call_time):
        return (False, "Not a business day (weekend or holiday)")

    # Check 2: Medical Guardian hours (9 AM - 5 PM EST)?
    mg_time = call_time.astimezone(MG_TIMEZONE)
    if not (9 <= mg_time.hour < 17):
        return (False, f"Outside MG hours (current: {mg_time.strftime('%I:%M %p EST')})")

    # Check 3: Member hours (9 AM - 5 PM member timezone)?
    member_time = call_time.astimezone(member_timezone)
    if not (9 <= member_time.hour < 17):
        return (False, f"Outside member hours (current: {member_time.strftime('%I:%M %p')})")

    # ✅ All checks passed
    return (True, "Call allowed")
```

### Valid Calling Windows by Timezone

| Member Timezone | EST Offset | Valid Hours (EST) | Valid Hours (Local) | Window Duration |
|-----------------|------------|-------------------|---------------------|-----------------|
| **EST** (New York) | 0 hours | 9:00 AM - 5:00 PM | 9:00 AM - 5:00 PM | 8 hours |
| **CST** (Chicago) | -1 hour | 10:00 AM - 5:00 PM | 9:00 AM - 4:00 PM | 7 hours |
| **MST** (Denver) | -2 hours | 11:00 AM - 5:00 PM | 9:00 AM - 3:00 PM | 6 hours |
| **PST** (California) | -3 hours | 12:00 PM - 5:00 PM | 9:00 AM - 2:00 PM | 5 hours |

**Note:** As members move further west, the calling window narrows!

---

## Use Case 1: Member in EST Timezone

### Member Profile
- **Name:** John Smith
- **Phone:** +15551234567
- **Timezone:** America/New_York (EST)
- **Device Delivered:** Monday, Jan 1, 2025
- **Activation Start:** Wednesday, Jan 3, 2025 (Delivery + 2 business days)

---

### CALL 1 - First Attempt (Day 3: Wednesday, Jan 3)

**When Eligible:**
- Frequency: activation_start_date
- Earliest: Wednesday, Jan 3, 2025

#### Scenario 1: 8:30 AM EST - ❌ TOO EARLY

```
⏰ Scheduler Run: 8:30 AM EST (Wednesday, Jan 3)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Wednesday, not holiday)
   ❌ Is it 9 AM - 5 PM EST? NO (8:30 AM is before 9 AM)
   ❌ Is it 9 AM - 5 PM member time? NO (8:30 AM EST = too early)

📋 Decision: ❌ Skip this member
⏭️ Next Check: 8:45 AM scheduler run (15 min interval)
```

#### Scenario 2: 9:00 AM EST - ✅ FIRST VALID TIME

```
⏰ Scheduler Run: 9:00 AM EST (Wednesday, Jan 3)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Wednesday)
   ✅ Is it 9 AM - 5 PM EST? YES (9:00 AM = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (9:00 AM EST = valid)

📋 Decision: ✅ CALL 1 MADE

📞 Call Details:
   - Bland AI Call ID: abc-123-def-456
   - Call Time: Wednesday, Jan 3, 2025 at 9:00 AM EST
   - Disposition: NoAnswer (member didn't pick up)
   - Next Eligible: Friday, Jan 5 (Call 1 + 2 calendar days)

📊 Database Update:
   INSERT INTO outreach_attempts (
       enrollment_id, attempt_ts, disposition, call_attempt_number
   ) VALUES (
       'enrollment-123', '2025-01-03 09:00:00', 'NoAnswer', 1
   )
```

---

### CALL 2 - Second Attempt (Day 5: Friday, Jan 5)

**When Eligible:**
- Frequency: Call 1 + 2 calendar days
- Earliest: Friday, Jan 5, 2025

#### Scenario: 10:15 AM EST - ✅ VALID

```
⏰ Scheduler Run: 10:15 AM EST (Friday, Jan 5)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 3 → Jan 5 = 2 calendar days)
   ✅ Device activated? NO (device_activated = 0)
   ✅ Previous attempts: 1 (Call 1 only)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Friday, not holiday)
   ✅ Is it 9 AM - 5 PM EST? YES (10:15 AM = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (10:15 AM EST = valid)

📋 Decision: ✅ CALL 2 MADE

📞 Call Details:
   - Call Time: Friday, Jan 5, 2025 at 10:15 AM EST
   - Disposition: Failed (member hung up)
   - Next Eligible: Sunday, Jan 7 (Call 2 + 2 calendar days)
     → Actual call: Monday, Jan 8 (Sunday is weekend)
```

---

### CALL 3 - Third Attempt (Day 7: Sunday → Monday)

**When Eligible:**
- Frequency: Call 2 + 2 calendar days
- Earliest: Sunday, Jan 7, 2025

#### Scenario 1: 11:00 AM EST on Sunday - ❌ WEEKEND

```
⏰ Scheduler Run: 11:00 AM EST (Sunday, Jan 7)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 5 → Jan 7 = 2 calendar days)
   ✅ Device activated? NO
   ✅ Previous attempts: 2 (Call 1, Call 2)

🔍 Business Hours Check:
   ❌ Is it a business day? NO (Sunday = weekend)

📋 Decision: ❌ Skip - No calls on weekends
⏭️ Next Check: Monday, Jan 8 at 9:00 AM
```

#### Scenario 2: 2:30 PM EST on Monday - ✅ VALID

```
⏰ Scheduler Run: 2:30 PM EST (Monday, Jan 8)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (still eligible, now 3 days since Call 2)
   ✅ Device activated? NO
   ✅ Previous attempts: 2

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Monday, not holiday)
   ✅ Is it 9 AM - 5 PM EST? YES (2:30 PM = 14:30 = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (2:30 PM EST = valid)

📋 Decision: ✅ CALL 3 MADE

📞 Call Details:
   - Call Time: Monday, Jan 8, 2025 at 2:30 PM EST
   - Disposition: NotInterested (member said "call me later")
   - Next Eligible: Saturday, Jan 13 (Call 3 + 5 calendar days)
     → Actual call: Monday, Jan 15 (weekend skipped)
```

---

### CALL 4 - Fourth Attempt (Day 13: Saturday → Monday)

**When Eligible:**
- Frequency: Call 3 + 5 calendar days
- Earliest: Saturday, Jan 13, 2025

#### Scenario 1: 10:00 AM EST on Saturday - ❌ WEEKEND

```
⏰ Scheduler Run: 10:00 AM EST (Saturday, Jan 13)

🔍 Business Hours Check:
   ❌ Is it a business day? NO (Saturday = weekend)

📋 Decision: ❌ Skip - Wait for Monday
⏭️ Next Check: Monday, Jan 15 at 9:00 AM
```

#### Scenario 2: 4:45 PM EST on Monday - ✅ LAST HOUR

```
⏰ Scheduler Run: 4:45 PM EST (Monday, Jan 15)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 8 → Jan 15 = 7 days, >= 5 required)
   ✅ Device activated? NO
   ✅ Previous attempts: 3 (Call 1, 2, 3)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Monday)
   ✅ Is it 9 AM - 5 PM EST? YES (4:45 PM = 16:45, still before 5 PM)
   ✅ Is it 9 AM - 5 PM member time? YES (4:45 PM EST = valid)

📋 Decision: ✅ CALL 4 MADE

📞 Call Details:
   - Call Time: Monday, Jan 15, 2025 at 4:45 PM EST
   - Disposition: NoAnswer (member didn't pick up again)
   - Next Eligible: Monday, Jan 22 (Call 4 + 7 calendar days)
```

#### Scenario 3: 5:15 PM EST - ❌ TOO LATE

```
⏰ If Scheduler Ran: 5:15 PM EST (Monday, Jan 15)

🔍 Business Hours Check:
   ✅ Is it a business day? YES
   ❌ Is it 9 AM - 5 PM EST? NO (5:15 PM = after 5 PM cutoff)

📋 Decision: ❌ Too late today
⏭️ Next Check: Tomorrow (Tuesday) at 9:00 AM

💡 Note: Member would be eligible tomorrow since frequency already passed
```

---

### CALL 5 - Fifth Attempt 🚨 90-DAY WINDOW STARTS!

**When Eligible:**
- Frequency: Call 4 + 7 calendar days
- Earliest: Monday, Jan 22, 2025

#### Scenario: 11:30 AM EST - ✅ VALID

```
⏰ Scheduler Run: 11:30 AM EST (Monday, Jan 22)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 15 → Jan 22 = 7 calendar days)
   ✅ Device activated? NO
   ✅ Previous attempts: 4 (Call 1, 2, 3, 4)
   ✅ call_5_timestamp? NULL (haven't reached Call 5 yet)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Monday)
   ✅ Is it 9 AM - 5 PM EST? YES (11:30 AM = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (11:30 AM EST = valid)

📋 Decision: ✅ CALL 5 MADE

📞 Call Details:
   - Call Time: Monday, Jan 22, 2025 at 11:30 AM EST
   - Disposition: NotInterested (member answered but didn't activate)
   - Next Eligible: Monday, Jan 29 (Call 5 + 7 days)

🚨 SPECIAL DATABASE UPDATE (Batch Orchestrator):
   UPDATE member_campaign_enrollments_enhanced
   SET
       call_5_timestamp = '2025-01-22 11:30:00-05:00',
       campaign_end_date = '2025-04-22'  -- Jan 22 + 90 days
   WHERE enrollment_id = 'enrollment-123'
   AND call_5_timestamp IS NULL
   AND (SELECT COUNT(*) FROM outreach_attempts
        WHERE enrollment_id = 'enrollment-123') = 5

📊 Campaign Timeline Updated:
   - 90-Day Window Start: Jan 22, 2025 at 11:30 AM EST
   - 90-Day Window End: April 22, 2025
   - Remaining Time: 90 days (13 weeks)
   - Max Possible Calls: ~13 more weekly calls (Call 6-18)
```

---

### CALL 6 - Sixth Attempt (Day 29: Monday, Jan 29)

**When Eligible:**
- Frequency: Call 5 + 7 calendar days
- Earliest: Monday, Jan 29, 2025

#### Scenario: 1:00 PM EST - ✅ VALID

```
⏰ Scheduler Run: 1:00 PM EST (Monday, Jan 29)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 22 → Jan 29 = 7 calendar days)
   ✅ Device activated? NO
   ✅ Previous attempts: 5
   ✅ call_5_timestamp set? YES (Jan 22, 2025)
   ✅ Within 90-day window? YES (Jan 29 < April 22)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Monday)
   ✅ Is it 9 AM - 5 PM EST? YES (1:00 PM = 13:00 = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (1:00 PM EST = valid)

📋 Decision: ✅ CALL 6 MADE

📞 Call Details:
   - Call Time: Monday, Jan 29, 2025 at 1:00 PM EST
   - Disposition: NoAnswer
   - Next Eligible: Monday, Feb 5 (Call 6 + 7 days)
   - Days Remaining in Campaign: 83 days (until April 22)
```

---

### CALL 7 - Seventh Attempt (Day 36: Monday, Feb 5)

**When Eligible:**
- Frequency: Call 6 + 7 calendar days
- Earliest: Monday, Feb 5, 2025

#### Scenario: 9:15 AM EST - ✅ VALID (Success!)

```
⏰ Scheduler Run: 9:15 AM EST (Monday, Feb 5)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 29 → Feb 5 = 7 calendar days)
   ✅ Device activated? NO
   ✅ Previous attempts: 6
   ✅ call_5_timestamp set? YES (Jan 22, 2025)
   ✅ Within 90-day window? YES (Feb 5 < April 22)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Monday)
   ✅ Is it 9 AM - 5 PM EST? YES (9:15 AM = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (9:15 AM EST = valid)

📋 Decision: ✅ CALL 7 MADE

📞 Call Details:
   - Call Time: Monday, Feb 5, 2025 at 9:15 AM EST
   - Disposition: Interested (Finally!)
   - Member Response: "Yes, I'd like to activate my device now"
   - Call Outcome: ✅ DEVICE ACTIVATED DURING CALL

🎉 WEBHOOK RECEIVED (Bland AI → Database):
   {
       "call_id": "abc-123-def-456",
       "disposition": "INTERESTED",
       "metadata": {
           "device_activated": true,
           "activation_confirmed": true
       }
   }

📊 Database Update (Webhook Handler):
   UPDATE member_campaign_enrollments_enhanced
   SET
       current_status = 'COMPLETED',
       device_activated = 1,
       completion_ts = SYSDATETIMEOFFSET()
   WHERE enrollment_id = 'enrollment-123'

   UPDATE outreach_attempts
   SET disposition = 'Completed'
   WHERE attempt_id = 'call-7-attempt-id'

🏁 Campaign Completed:
   - Total Calls Made: 7
   - Total Days: 36 days (Jan 1 → Feb 5)
   - Campaign Status: COMPLETED
   - Device Status: ✅ ACTIVATED
   - No more calls will be made
```

---

## Use Case 2: Member in PST Timezone

### Member Profile
- **Name:** Maria Garcia
- **Phone:** +15559876543
- **Timezone:** America/Los_Angeles (PST)
- **Device Delivered:** Monday, Jan 1, 2025
- **Activation Start:** Wednesday, Jan 3, 2025

**Key Challenge:** 3-hour time difference creates narrow calling window!

---

### CALL 1 - Wednesday, Jan 3, 2025

#### Scenario 1: 9:00 AM EST = 6:00 AM PST - ❌ TOO EARLY

```
⏰ Scheduler Run: 9:00 AM EST (Wednesday, Jan 3)

🌍 Timezone Conversion:
   - Medical Guardian Time: 9:00 AM EST ✅
   - Member Local Time: 6:00 AM PST ❌

🔍 Business Hours Check:
   ✅ Is it 9 AM - 5 PM EST? YES (9:00 AM EST)
   ❌ Is it 9 AM - 5 PM member time? NO (6:00 AM PST = before 9 AM)

📋 Decision: ❌ Too early for California member
⏭️ Next Check: Wait until 12:00 PM EST = 9:00 AM PST

💡 Explanation:
   Member is still sleeping at 6:00 AM PST
   Must wait 3 more hours for member's 9 AM
```

#### Scenario 2: 12:00 PM EST = 9:00 AM PST - ✅ FIRST VALID

```
⏰ Scheduler Run: 12:00 PM EST (noon)

🌍 Timezone Conversion:
   - Medical Guardian Time: 12:00 PM EST (noon) ✅
   - Member Local Time: 9:00 AM PST ✅

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Wednesday)
   ✅ Is it 9 AM - 5 PM EST? YES (12:00 PM = noon EST)
   ✅ Is it 9 AM - 5 PM member time? YES (9:00 AM PST = exactly 9 AM)

📋 Decision: ✅ CALL 1 MADE

📞 Call Details:
   - Call Time: Wednesday, Jan 3 at 12:00 PM EST (9:00 AM PST)
   - Disposition: NoAnswer
   - Next Eligible: Friday, Jan 5

⏰ Valid Calling Window for PST Members:
   - EST Window: 12:00 PM - 5:00 PM EST (5 hours)
   - PST Window: 9:00 AM - 2:00 PM PST (5 hours)
   - Much narrower than EST members!
```

#### Scenario 3: 5:30 PM EST = 2:30 PM PST - ❌ TOO LATE

```
⏰ If Scheduler Ran: 5:30 PM EST

🌍 Timezone Conversion:
   - Medical Guardian Time: 5:30 PM EST ❌ (after 5 PM)
   - Member Local Time: 2:30 PM PST ✅ (still valid)

🔍 Business Hours Check:
   ❌ Is it 9 AM - 5 PM EST? NO (5:30 PM = after MG closes)
   ✅ Is it 9 AM - 5 PM member time? YES (2:30 PM PST = valid)

📋 Decision: ❌ Medical Guardian closed (EST hours expired)
⏭️ Next Check: Tomorrow at 12:00 PM EST

💡 Note: Even though member's timezone is valid,
         MG closes at 5 PM EST, so no calls after that
```

---

### CALL 2 - Friday, Jan 5, 2025

#### Scenario 1: 3:30 PM EST = 12:30 PM PST - ✅ VALID

```
⏰ Scheduler Run: 3:30 PM EST (Friday, Jan 5)

🌍 Timezone Conversion:
   - Medical Guardian Time: 3:30 PM EST (15:30) ✅
   - Member Local Time: 12:30 PM PST ✅

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 3 → Jan 5 = 2 calendar days)
   ✅ Device activated? NO
   ✅ Previous attempts: 1

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Friday)
   ✅ Is it 9 AM - 5 PM EST? YES (3:30 PM = 15:30 = valid)
   ✅ Is it 9 AM - 5 PM member time? YES (12:30 PM PST = valid)

📋 Decision: ✅ CALL 2 MADE

📞 Call Details:
   - Call Time: Friday, Jan 5 at 3:30 PM EST (12:30 PM PST)
   - Disposition: Failed
   - Next Eligible: Sunday, Jan 7 → Monday, Jan 8
```

#### Scenario 2: 7:00 PM EST = 4:00 PM PST - ❌ TOO LATE

```
⏰ If Scheduler Ran: 7:00 PM EST

🌍 Timezone Conversion:
   - Medical Guardian Time: 7:00 PM EST ❌ (way after hours)
   - Member Local Time: 4:00 PM PST ✅ (still within 5 PM)

🔍 Business Hours Check:
   ❌ Is it 9 AM - 5 PM EST? NO (7:00 PM = after hours)
   ✅ Is it 9 AM - 5 PM member time? YES (4:00 PM PST = valid)

📋 Decision: ❌ Medical Guardian closed (EST hours expired)

💡 Lesson: MG hours (9 AM - 5 PM EST) always takes precedence
           Even if member's local time is valid
```

---

### CALL 3 - Tuesday, Jan 9, 2025 (Monday was MLK Day)

#### Scenario 1: Monday, Jan 8 - ❌ FEDERAL HOLIDAY

```
⏰ Scheduler Run: 1:00 PM EST (Monday, Jan 8)

🌍 Timezone Conversion:
   - Medical Guardian Time: 1:00 PM EST ✅
   - Member Local Time: 10:00 AM PST ✅

🔍 Business Hours Check:
   ❌ Is it a business day? NO (Martin Luther King Jr. Day)

📋 Decision: ❌ Skip - Federal holiday (observed nationwide)
⏭️ Next Check: Tuesday, Jan 9

📅 Holiday Info:
   - Holiday Name: Martin Luther King Jr. Day
   - Observed: 3rd Monday of January
   - Applies to ALL US timezones
   - No calls made on this day
```

#### Scenario 2: Tuesday 2:00 PM EST = 11:00 AM PST - ✅ VALID

```
⏰ Scheduler Run: 2:00 PM EST (Tuesday, Jan 9)

🌍 Timezone Conversion:
   - Medical Guardian Time: 2:00 PM EST (14:00) ✅
   - Member Local Time: 11:00 AM PST ✅

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Jan 5 → Jan 9 = 4 days, >= 2 required)
   ✅ Device activated? NO
   ✅ Previous attempts: 2

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Tuesday, not holiday)
   ✅ Is it 9 AM - 5 PM EST? YES (2:00 PM = 14:00)
   ✅ Is it 9 AM - 5 PM member time? YES (11:00 AM PST)

📋 Decision: ✅ CALL 3 MADE

📞 Call Details:
   - Call Time: Tuesday, Jan 9 at 2:00 PM EST (11:00 AM PST)
   - Disposition: NotInterested
   - Next Eligible: Sunday, Jan 14 → Monday, Jan 15 (Call 3 + 5 days)
```

---

### Valid Calling Window Summary (PST)

**Daily Window:**
```
EST Time          PST Time         Status
---------         ---------        ------
9:00 AM EST   →   6:00 AM PST     ❌ Too early (member sleeping)
10:00 AM EST  →   7:00 AM PST     ❌ Too early
11:00 AM EST  →   8:00 AM PST     ❌ Too early
12:00 PM EST  →   9:00 AM PST     ✅ VALID WINDOW STARTS
1:00 PM EST   →   10:00 AM PST    ✅ Valid
2:00 PM EST   →   11:00 AM PST    ✅ Valid
3:00 PM EST   →   12:00 PM PST    ✅ Valid
4:00 PM EST   →   1:00 PM PST     ✅ Valid
4:59 PM EST   →   1:59 PM PST     ✅ VALID WINDOW ENDS
5:00 PM EST   →   2:00 PM PST     ❌ MG closed
6:00 PM EST   →   3:00 PM PST     ❌ MG closed
```

**Key Observations:**
- ⏰ **5-hour window** for PST members (12 PM - 5 PM EST)
- 📉 **38% narrower** than EST members (8-hour window)
- 🌅 **No morning calls** possible (6-8 AM PST too early)
- 🌆 **No afternoon calls** after 2 PM PST (5 PM EST cutoff)

---

## Use Case 3: Calls During Holidays

### Christmas Week Example

**Member Profile:**
- Timezone: EST
- Device Delivered: Monday, Dec 22, 2025

---

### Scenario 1: Call 2 on Christmas Eve

```
📅 Timeline:
Dec 22 (Monday): Call 1 made at 10 AM EST
Dec 24 (Wednesday): Frequency check passes (2 calendar days)

⏰ Scheduler Run: 10:00 AM EST (Wednesday, Dec 24)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Dec 22 → Dec 24 = 2 days)
   ✅ Device activated? NO
   ✅ Previous attempts: 1

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Wednesday, not a federal holiday)
   ✅ Is it 9 AM - 5 PM EST? YES (10:00 AM EST)
   ✅ Is it 9 AM - 5 PM member time? YES (10:00 AM EST)

📋 Decision: ✅ CALL 2 MADE

📞 Call Details:
   - Call Time: Wednesday, Dec 24 at 10:00 AM EST
   - Disposition: NoAnswer
   - Next Eligible: Friday, Dec 26 (Dec 24 + 2 days)

💡 Note: Dec 24 (Christmas Eve) is NOT a federal holiday
         Calls can be made on this day
```

---

### Scenario 2: Call 3 on Christmas Day

```
📅 Timeline:
Dec 24 (Wednesday): Call 2 made at 10 AM EST
Dec 25 (Thursday): Frequency check passes (2 calendar days)
                    BUT Christmas Day = Federal Holiday

⏰ Scheduler Run: 11:00 AM EST (Thursday, Dec 25)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Dec 24 → Dec 25 = 1 day... wait, need 2!)
   Actually: Would be eligible Dec 26

🔍 Business Hours Check (if frequency passed):
   ❌ Is it a business day? NO (Christmas Day = federal holiday)

📋 Decision: ❌ No calls on Dec 25 - Christmas Day

🎄 Holiday Info:
   - Holiday Name: Christmas Day
   - Date: Dec 25, 2025 (Thursday)
   - System recognizes: holidays.US(observed=True)
   - All members: No calls today

⏭️ Next Check: Friday, Dec 26 at 9:00 AM EST
```

---

### Scenario 3: Call 3 on Day After Christmas

```
📅 Timeline:
Dec 24 (Wednesday): Call 2 made at 10 AM EST
Dec 26 (Friday): Frequency check passes (2 calendar days)

⏰ Scheduler Run: 2:00 PM EST (Friday, Dec 26)

🔍 Eligibility Check:
   ✅ Frequency passed? YES (Dec 24 → Dec 26 = 2 days)
   ✅ Device activated? NO
   ✅ Previous attempts: 2

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Friday, not holiday)
   ✅ Is it 9 AM - 5 PM EST? YES (2:00 PM = 14:00)
   ✅ Is it 9 AM - 5 PM member time? YES (2:00 PM EST)

📋 Decision: ✅ CALL 3 MADE

📞 Call Details:
   - Call Time: Friday, Dec 26 at 2:00 PM EST
   - Disposition: Interested
   - Next Eligible: Wednesday, Dec 31 (Dec 26 + 5 days)

📊 Impact of Christmas:
   - Call 2 → Call 3: Expected 2 days, actual 2 days
   - No delay because Christmas fell AFTER eligible date
   - If Call 2 was Dec 23, Call 3 would skip Dec 25
```

---

### Scenario 4: New Year's Week

```
📅 Timeline:
Dec 26 (Friday): Call 3 made at 2 PM EST
Dec 31 (Wednesday): Frequency check passes (Call 3 + 5 days)
Jan 1 (Thursday): New Year's Day = Federal Holiday

⏰ Scheduler Run: 10:00 AM EST (Wednesday, Dec 31)

🔍 Business Hours Check:
   ✅ Is it a business day? YES (Dec 31 is NOT a federal holiday)
   ✅ Is it 9 AM - 5 PM EST? YES (10:00 AM EST)

📋 Decision: ✅ CALL 4 MADE on Dec 31

📞 Call Details:
   - Call Time: Wednesday, Dec 31 at 10:00 AM EST
   - Disposition: NoAnswer
   - Next Eligible: Wednesday, Jan 7 (Dec 31 + 7 days)

⏰ Next Day (New Year's Day):
   - Jan 1 (Thursday): Federal Holiday - No calls
   - If Call 4 was Jan 1 eligible, would skip to Jan 2 (Friday)
```

---

### Holiday Impact Summary

| Scenario | Expected Date | Holiday Encountered | Actual Call Date | Delay |
|----------|---------------|---------------------|------------------|-------|
| Call 2 | Dec 24 | None | Dec 24 | 0 days |
| Call 3 | Dec 26 | Dec 25 (Christmas) | Dec 26 | 0 days (already after) |
| Call 4 | Dec 31 | None | Dec 31 | 0 days |
| Call 5 | Jan 7 | Jan 1 (New Year) | Jan 7 | 0 days (already after) |

**Key Insight:** Holidays only delay calls if the **eligible date falls ON the holiday**. If eligible date is before/after, no delay occurs.

---

## Use Case 4: Weekend Handling

### Friday Call → Weekend → Monday Call Example

**Member Profile:**
- Timezone: EST
- Device Delivered: Monday, Jan 1, 2025

---

### Scenario: Call 2 Eligible on Sunday

```
📅 Timeline:
Day 3 (Wednesday, Jan 3): Call 1 made at 10 AM EST
Day 5 (Friday, Jan 5): Eligible for Call 2 (Call 1 + 2 days)
Day 7 (Sunday, Jan 7): Would be Call 2 + 2 days for Call 3

🔍 Scheduler Runs Through Weekend:

┌─────────────────────────────────────────────────────────┐
│ Friday, Jan 5 at 3:00 PM EST                           │
├─────────────────────────────────────────────────────────┤
│ ✅ Eligibility: YES (2 days since Call 1)              │
│ ✅ Business Day: YES (Friday)                          │
│ ✅ Business Hours: YES (3 PM = 15:00 EST)             │
│                                                         │
│ Result: ✅ CALL 2 MADE                                 │
│ Disposition: Failed                                     │
│ Next Eligible: Sunday, Jan 7 (Call 2 + 2 days)        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Saturday, Jan 6 at 10:00 AM EST                        │
├─────────────────────────────────────────────────────────┤
│ ✅ Eligibility: YES (1 day since Call 2)               │
│ ❌ Business Day: NO (Saturday = weekend)               │
│                                                         │
│ Result: ❌ SKIP - No calls on weekends                 │
│ Scheduler logs: "Skipped - Saturday"                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Sunday, Jan 7 at 11:00 AM EST                          │
├─────────────────────────────────────────────────────────┤
│ ✅ Eligibility: YES (2 days since Call 2)              │
│ ❌ Business Day: NO (Sunday = weekend)                 │
│                                                         │
│ Result: ❌ SKIP - No calls on weekends                 │
│ Scheduler logs: "Skipped - Sunday"                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Monday, Jan 8 at 9:00 AM EST                           │
├─────────────────────────────────────────────────────────┤
│ ✅ Eligibility: YES (3 days since Call 2, >= 2 needed) │
│ ✅ Business Day: YES (Monday)                          │
│ ✅ Business Hours: YES (9:00 AM EST)                   │
│                                                         │
│ Result: ✅ CALL 3 MADE                                 │
│ Disposition: NoAnswer                                   │
│ Actual Days Since Call 2: 3 calendar days              │
└─────────────────────────────────────────────────────────┘
```

---

### Weekend Pattern Analysis

**Pattern 1: Call on Friday → Skip Weekend → Call on Monday**
```
Friday 3 PM   →  Call made
Saturday      →  Skipped (weekend)
Sunday        →  Skipped (weekend)
Monday 9 AM   →  Call made (if eligible)

Delay: 0 days (calendar days still count)
```

**Pattern 2: Call on Thursday → Eligible Saturday → Call on Monday**
```
Thursday 2 PM →  Call made
Friday        →  (Only 1 day passed, need 2)
Saturday      →  Eligible but weekend
Sunday        →  Still weekend
Monday 9 AM   →  Call made

Delay: 2 calendar days (Sat+Sun), but frequency rule satisfied
```

**Pattern 3: Call on Wednesday → Eligible Friday → Call on Friday**
```
Wednesday 10 AM → Call made
Thursday         → (Only 1 day passed)
Friday 2 PM      → Eligible + Business day

Result: Call made Friday (no weekend delay)
```

---

### Multiple Weekend Scenarios

#### Scenario A: 5-Day Frequency Hits Saturday

```
📅 Timeline:
Monday, Jan 8: Call 3 made
       ↓ (5 calendar days)
Saturday, Jan 13: Eligible for Call 4

⏰ What Happens:
- Saturday, Jan 13: Skipped (weekend)
- Sunday, Jan 14: Skipped (weekend)
- Monday, Jan 15: ✅ CALL 4 MADE

📊 Analysis:
- Frequency requirement: Met (5+ days passed)
- Business day requirement: Met Monday
- Actual call: 7 calendar days after Call 3
- Extra wait: 2 days (weekend)
```

#### Scenario B: 7-Day Frequency Hits Sunday

```
📅 Timeline:
Monday, Jan 22: Call 5 made
       ↓ (7 calendar days)
Monday, Jan 29: Eligible for Call 6 ✅

⏰ What Happens:
- Sunday, Jan 28: Would be 6 days (not eligible anyway)
- Monday, Jan 29: ✅ CALL 6 MADE (exactly 7 days)

📊 Analysis:
- Lucky! 7 days from Monday = next Monday
- No weekend delay
- Weekly pattern aligns with business days
```

---

## Use Case 5: Multi-Timezone Scenarios

### Scenario 1: CST Member (Chicago)

**Member Profile:**
- Timezone: America/Chicago (CST)
- Offset: -1 hour from EST

---

#### Valid Calling Window

```
EST Time          CST Time         Status
---------         ---------        ------
9:00 AM EST   →   8:00 AM CST     ❌ Too early (member before 9 AM)
10:00 AM EST  →   9:00 AM CST     ✅ VALID WINDOW STARTS
11:00 AM EST  →   10:00 AM CST    ✅ Valid
12:00 PM EST  →   11:00 AM CST    ✅ Valid
1:00 PM EST   →   12:00 PM CST    ✅ Valid
2:00 PM EST   →   1:00 PM CST     ✅ Valid
3:00 PM EST   →   2:00 PM CST     ✅ Valid
4:00 PM EST   →   3:00 PM CST     ✅ Valid
4:59 PM EST   →   3:59 PM CST     ✅ VALID WINDOW ENDS
5:00 PM EST   →   4:00 PM CST     ❌ MG closed
```

**Valid Window:** 10:00 AM - 5:00 PM EST (7 hours)

---

#### Example Call

```
⏰ Scheduler Run: 1:30 PM EST

🌍 Timezone Conversion:
   - Medical Guardian Time: 1:30 PM EST (13:30) ✅
   - Member Local Time: 12:30 PM CST ✅

🔍 Business Hours Check:
   ✅ Is it a business day? YES
   ✅ Is it 9 AM - 5 PM EST? YES (1:30 PM = 13:30)
   ✅ Is it 9 AM - 5 PM member time? YES (12:30 PM CST)

📋 Decision: ✅ CALL MADE

📞 Call Time Display:
   - System Log: 2025-01-03 13:30:00-05:00 (EST)
   - Member Experience: 12:30 PM CST (lunch time)
```

---

### Scenario 2: MST Member (Denver)

**Member Profile:**
- Timezone: America/Denver (MST)
- Offset: -2 hours from EST

---

#### Valid Calling Window

```
EST Time          MST Time         Status
---------         ---------        ------
9:00 AM EST   →   7:00 AM MST     ❌ Too early
10:00 AM EST  →   8:00 AM MST     ❌ Too early
11:00 AM EST  →   9:00 AM MST     ✅ VALID WINDOW STARTS
12:00 PM EST  →   10:00 AM MST    ✅ Valid
1:00 PM EST   →   11:00 AM MST    ✅ Valid
2:00 PM EST   →   12:00 PM MST    ✅ Valid
3:00 PM EST   →   1:00 PM MST     ✅ Valid
4:00 PM EST   →   2:00 PM MST     ✅ Valid
4:59 PM EST   →   2:59 PM MST     ✅ VALID WINDOW ENDS
5:00 PM EST   →   3:00 PM MST     ❌ MG closed
```

**Valid Window:** 11:00 AM - 5:00 PM EST (6 hours)

---

#### Example Call

```
⏰ Scheduler Run: 3:00 PM EST

🌍 Timezone Conversion:
   - Medical Guardian Time: 3:00 PM EST (15:00) ✅
   - Member Local Time: 1:00 PM MST ✅

🔍 Business Hours Check:
   ✅ Is it a business day? YES
   ✅ Is it 9 AM - 5 PM EST? YES (3:00 PM = 15:00)
   ✅ Is it 9 AM - 5 PM member time? YES (1:00 PM MST)

📋 Decision: ✅ CALL MADE

⚠️ Note:
   - Still 2 hours left in calling window!
   - After 5 PM EST (3 PM MST), MG closes
   - MST members have narrower window than CST
```

---

### Scenario 3: Mixed Timezone Batch

**Batch contains members from all 4 US timezones:**

```
⏰ Scheduler Run: 12:00 PM EST (Noon)

📊 Batch Analysis:
   - Total Members Eligible: 100
   - EST Members: 40
   - CST Members: 30
   - MST Members: 20
   - PST Members: 10

🔍 Business Hours Check Results:

┌─────────────────────────────────────────────────────────┐
│ EST Members (40 members)                                │
├─────────────────────────────────────────────────────────┤
│ MG Time: 12:00 PM EST ✅                                │
│ Member Time: 12:00 PM EST ✅                            │
│ Result: ✅ ALL 40 eligible for calling                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ CST Members (30 members)                                │
├─────────────────────────────────────────────────────────┤
│ MG Time: 12:00 PM EST ✅                                │
│ Member Time: 11:00 AM CST ✅                            │
│ Result: ✅ ALL 30 eligible for calling                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ MST Members (20 members)                                │
├─────────────────────────────────────────────────────────┤
│ MG Time: 12:00 PM EST ✅                                │
│ Member Time: 10:00 AM MST ✅                            │
│ Result: ✅ ALL 20 eligible for calling                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ PST Members (10 members)                                │
├─────────────────────────────────────────────────────────┤
│ MG Time: 12:00 PM EST ✅                                │
│ Member Time: 9:00 AM PST ✅ (just opened!)              │
│ Result: ✅ ALL 10 eligible for calling                  │
└─────────────────────────────────────────────────────────┘

📋 Batch Summary:
   - Total Submitted to Bland AI: 100 calls
   - Batch ID: batch-456-789
   - Submission Time: 12:00 PM EST
   - All timezones satisfied ✅

💡 Best Practice:
   12:00 PM EST (noon) is the OPTIMAL time for multi-timezone batches
   - All 4 US timezones are in valid window
   - Maximum coverage across continental US
```

---

### Timezone Window Comparison

| Timezone | Offset | Valid Window (EST) | Valid Window (Local) | Duration | % of Day |
|----------|--------|-------------------|---------------------|----------|----------|
| EST | 0 hrs | 9 AM - 5 PM | 9 AM - 5 PM | 8 hours | 33% |
| CST | -1 hr | 10 AM - 5 PM | 9 AM - 4 PM | 7 hours | 29% |
| MST | -2 hrs | 11 AM - 5 PM | 9 AM - 3 PM | 6 hours | 25% |
| PST | -3 hrs | 12 PM - 5 PM | 9 AM - 2 PM | 5 hours | 21% |

**Key Insights:**
- 📉 Window narrows by 1 hour per timezone westward
- ⏰ Noon EST is universally valid for all timezones
- 🌅 PST members have 38% narrower window than EST
- 🎯 Best batch submission time: 12:00 PM - 3:00 PM EST

---

## Decision Logic Reference

### Calls 1-4 Decision Tree

```
START: Member in database with device delivered

├─ Is activation_start_date in the past?
│  ├─ NO → Wait for activation_start_date
│  └─ YES → Continue
│
├─ Is device already activated?
│  ├─ YES → STOP (campaign complete)
│  └─ NO → Continue
│
├─ How many previous attempts?
│  ├─ 0 (No attempts yet)
│  │  └─ ✅ ELIGIBLE FOR CALL 1
│  │
│  ├─ 1 (Call 1 made)
│  │  ├─ Has 2+ calendar days passed?
│  │  │  ├─ NO → Wait
│  │  │  └─ YES → Check business hours → CALL 2
│  │
│  ├─ 2 (Call 1, 2 made)
│  │  ├─ Has 2+ calendar days passed?
│  │  │  ├─ NO → Wait
│  │  │  └─ YES → Check business hours → CALL 3
│  │
│  └─ 3 (Call 1, 2, 3 made)
│     ├─ Has 5+ calendar days passed?
│     │  ├─ NO → Wait
│     │  └─ YES → Check business hours → CALL 4
│
└─ Business Hours Check (if frequency passed):
   ├─ Is today a business day (Mon-Fri, not holiday)?
   │  ├─ NO → Skip today, try tomorrow
   │  └─ YES → Continue
   │
   ├─ Is it 9 AM - 5 PM EST?
   │  ├─ NO → Skip this run, try next (15 min)
   │  └─ YES → Continue
   │
   └─ Is it 9 AM - 5 PM member local time?
      ├─ NO → Skip this run, try next
      └─ YES → ✅ MAKE THE CALL
```

---

### Calls 5+ Decision Tree

```
START: Member with 4+ previous attempts

├─ Is call_5_timestamp set?
│  ├─ NO (Haven't reached Call 5 yet)
│  │  ├─ Has 7+ calendar days passed since Call 4?
│  │  │  ├─ NO → Wait
│  │  │  └─ YES → Check business hours → CALL 5
│  │  │         └─ After Call 5: Set call_5_timestamp + campaign_end_date
│  │
│  └─ YES (Already made Call 5+)
│     ├─ Has 7+ calendar days passed since last call?
│     │  ├─ NO → Wait
│     │  └─ YES → Continue
│     │
│     ├─ Is today <= campaign_end_date?
│     │  ├─ NO → ❌ STOP (90-day window expired)
│     │  └─ YES → Continue
│     │
│     └─ Business Hours Check:
│        ├─ Is today a business day?
│        │  ├─ NO → Skip today
│        │  └─ YES → Continue
│        │
│        ├─ Is it 9 AM - 5 PM EST?
│        │  ├─ NO → Skip this run
│        │  └─ YES → Continue
│        │
│        └─ Is it 9 AM - 5 PM member local time?
│           ├─ NO → Skip this run
│           └─ YES → ✅ MAKE THE CALL (Call 6, 7, 8, ...)
```

---

### Business Hours Validation Flowchart

```
INPUT: current_time (UTC), member_timezone

├─ Convert to Medical Guardian timezone (EST)
│  └─ mg_time = current_time.astimezone('America/New_York')
│
├─ Convert to member's timezone
│  └─ member_time = current_time.astimezone(member_timezone)
│
├─ CHECK 1: Is it a business day?
│  ├─ Is today Saturday or Sunday?
│  │  └─ YES → ❌ FAIL ("Weekend")
│  │
│  ├─ Is today a US federal holiday?
│  │  └─ YES → ❌ FAIL ("Federal Holiday: {name}")
│  │
│  └─ NO → ✅ PASS (Continue to Check 2)
│
├─ CHECK 2: Medical Guardian Hours (9 AM - 5 PM EST)?
│  ├─ Is mg_time.hour < 9?
│  │  └─ YES → ❌ FAIL ("Before MG hours")
│  │
│  ├─ Is mg_time.hour >= 17? (5 PM = 17:00)
│  │  └─ YES → ❌ FAIL ("After MG hours")
│  │
│  └─ NO → ✅ PASS (Continue to Check 3)
│
└─ CHECK 3: Member Hours (9 AM - 5 PM local)?
   ├─ Is member_time.hour < 9?
   │  └─ YES → ❌ FAIL ("Before member hours")
   │
   ├─ Is member_time.hour >= 17? (5 PM = 17:00)
   │  └─ YES → ❌ FAIL ("After member hours")
   │
   └─ NO → ✅ PASS

RESULT: ✅ ALL CHECKS PASSED → Make the call!
```

---

## Troubleshooting Guide

### Issue 1: "Member is eligible but not being called"

**Symptoms:**
- Eligibility query returns member
- Frequency requirements met
- But call not submitted to Bland AI

**Debug Steps:**

1. **Check Business Hours Logs**
```
grep "ELIGIBILITY-SERVICE" application_insights.log | grep "Member {member_id}"

Expected Log:
✅ [ELIGIBILITY-SERVICE] Member abc-123 eligible: Call allowed - within both MG and member business hours

Actual Log (if failing):
⏰ [ELIGIBILITY-SERVICE] Member abc-123 not eligible: Call blocked - outside member business hours
```

2. **Verify Timezone**
```sql
SELECT
    m.member_id,
    m.timezone,
    SYSDATETIMEOFFSET() AS current_utc_time,
    SYSDATETIMEOFFSET() AT TIME ZONE m.timezone AS member_local_time
FROM engage360.members m
WHERE m.member_id = 'abc-123'
```

3. **Check Holiday Calendar**
```python
from af_code.shared.business_hours_utils import BusinessHoursValidator
import pytz
from datetime import datetime

now = datetime.now(pytz.UTC)
is_business_day = BusinessHoursValidator.is_business_day(now)
print(f"Is today a business day? {is_business_day}")

if not is_business_day:
    if now.weekday() >= 5:
        print("Reason: Weekend")
    elif now.date() in BusinessHoursValidator.US_HOLIDAYS:
        holiday_name = BusinessHoursValidator.US_HOLIDAYS.get(now.date())
        print(f"Reason: Federal Holiday ({holiday_name})")
```

---

### Issue 2: "PST members never getting called"

**Symptoms:**
- PST members appear in eligibility query
- All filtered out during business hours validation
- Calls only work for EST/CST members

**Root Cause:** Scheduler running outside PST valid window (12 PM - 5 PM EST)

**Solution:**
```
Check scheduler run times:
- Morning runs (9 AM - 11 AM EST): ❌ Won't work for PST (6-8 AM PST)
- Noon runs (12 PM - 2 PM EST): ✅ Optimal for PST
- Afternoon runs (3 PM - 5 PM EST): ✅ Works for PST

Recommendation: Ensure scheduler runs at least once between 12-5 PM EST daily
```

---

### Issue 3: "Call 5 timestamp not being set"

**Symptoms:**
- Member has 5+ outreach attempts
- `call_5_timestamp` still NULL
- `campaign_end_date` still NULL

**Debug Steps:**

1. **Check Batch Orchestrator Logs**
```
grep "BATCH-ORCHESTRATOR" application_insights.log | grep "PHASE 2.5"

Expected Log:
🕐 [BATCH-ORCHESTRATOR] PHASE 2.5: TRACK CALL 5 TIMESTAMP
✅ [BATCH-ORCHESTRATOR] Updated 3 enrollments:
   • Set call_5_timestamp to current timestamp
```

2. **Verify Call Count**
```sql
SELECT
    e.enrollment_id,
    e.member_id,
    e.call_5_timestamp,
    e.campaign_end_date,
    COUNT(oa.attempt_id) AS total_attempts
FROM engage360.member_campaign_enrollments_enhanced e
LEFT JOIN engage360.outreach_attempts oa
    ON e.enrollment_id = oa.enrollment_id
WHERE e.member_id = 'abc-123'
GROUP BY e.enrollment_id, e.member_id, e.call_5_timestamp, e.campaign_end_date
```

3. **Manual Fix (if needed)**
```sql
-- Only run if batch orchestrator failed to update
UPDATE engage360.member_campaign_enrollments_enhanced
SET
    call_5_timestamp = SYSDATETIMEOFFSET(),
    campaign_end_date = CAST(DATEADD(DAY, 90, SYSDATETIMEOFFSET()) AS DATE)
WHERE enrollment_id = 'abc-123'
AND call_5_timestamp IS NULL
AND (SELECT COUNT(*) FROM engage360.outreach_attempts
     WHERE enrollment_id = 'abc-123') >= 5
```

---

### Issue 4: "Calls happening on weekends/holidays"

**Symptoms:**
- Call logs show attempts on Saturday/Sunday
- Or on federal holidays (Christmas, etc.)

**Root Cause:** Business hours validation bypassed or failed

**Debug Steps:**

1. **Verify Validation Function**
```python
from af_code.shared.business_hours_utils import can_make_call
import pytz
from datetime import datetime

# Test with actual call timestamp
call_time = datetime(2025, 12, 25, 10, 0, tzinfo=pytz.UTC)  # Christmas 10 AM
member_tz = pytz.timezone('America/New_York')

can_call, reason = can_make_call(call_time, member_tz)
print(f"Can call? {can_call}")
print(f"Reason: {reason}")

# Expected output:
# Can call? False
# Reason: Call blocked - not a business day (weekend or holiday)
```

2. **Check Eligibility Service Integration**
```python
# In eligibility_service.py, verify this logic exists:
eligible_members = self._filter_by_business_hours(potential_members)
```

---

### Issue 5: "90-day window expired but calls still happening"

**Symptoms:**
- `campaign_end_date` = April 22, 2025
- Today = April 25, 2025
- Member still appearing in eligible query

**Debug Steps:**

1. **Check SQL WHERE Clause**
```sql
-- This should be in eligibility query:
AND (
    e.call_5_timestamp IS NULL  -- Calls 1-4
    OR
    SYSDATETIMEOFFSET() <= e.campaign_end_date  -- Call 5+
)
```

2. **Verify Database Values**
```sql
SELECT
    e.enrollment_id,
    e.call_5_timestamp,
    e.campaign_end_date,
    SYSDATETIMEOFFSET() AS current_time,
    CASE
        WHEN SYSDATETIMEOFFSET() <= e.campaign_end_date THEN 'Within window'
        ELSE 'Expired'
    END AS window_status
FROM engage360.member_campaign_enrollments_enhanced e
WHERE e.member_id = 'abc-123'
```

---

## Summary

This document provides comprehensive use cases covering:

✅ **Call Sequence**: Detailed examples of Calls 1-7+ with real timelines
✅ **Business Days**: Calendar days vs business days calculation
✅ **Holidays**: US federal holiday handling with examples
✅ **Business Hours**: Dual-timezone validation for all 4 US timezones
✅ **Weekend Handling**: How weekends affect call scheduling
✅ **Multi-Timezone**: EST, CST, MST, PST calling window analysis
✅ **Decision Logic**: Flowcharts and decision trees for all scenarios
✅ **Troubleshooting**: Common issues and debugging steps

**Key Takeaways:**

1. **Frequency = Calendar Days** (includes weekends)
2. **Timing = Business Days** (Mon-Fri, no holidays)
3. **Calls 1-4 = No 90-day limit** (can happen anytime)
4. **Call 5+ = 90-day window** from activation_start_date
5. **PST members = 5-hour window** (narrowest)
6. **Noon EST = Optimal time** for multi-timezone batches

---

**Document Status:** ✅ Complete
**Last Reviewed:** 2025-12-24
**Next Review:** 2026-01-24
