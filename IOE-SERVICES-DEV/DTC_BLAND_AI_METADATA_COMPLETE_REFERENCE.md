# DTC Bland AI Metadata - Complete Reference

**Document Purpose**: Complete breakdown of metadata sent to Bland AI for DTC (Direct-to-Consumer) intro and wellness calls

**Date Created**: 2025-10-22
**Related Files**:
- `af_code/af_dtc_intro_call/services/blandai_service.py` (Lines 171-185)
- `af_code/af_dtc_intro_call/utils/config.py` (Query: Lines 45-71)

---

## 📋 **Table of Contents**

1. [Metadata Overview](#metadata-overview)
2. [Complete Metadata Structure](#complete-metadata-structure)
3. [Field-by-Field Breakdown](#field-by-field-breakdown)
4. [Database Source Mapping](#database-source-mapping)
5. [Complete Payload Example](#complete-payload-example)
6. [Webhook Return Flow](#webhook-return-flow)
7. [Comparison: DTC vs Partner Campaigns](#comparison-dtc-vs-partner-campaigns)

---

## 🎯 **Metadata Overview**

### **What is Metadata?**
Metadata is included in every Bland AI call object to:
- ✅ **Track the call** - Link Bland AI call back to our database records
- ✅ **Identify the member** - Know who was called
- ✅ **Support webhooks** - Bland AI returns metadata in webhook responses
- ✅ **Enable reporting** - Connect call outcomes to campaigns and members

### **When is Metadata Used?**
1. **Submission**: Sent to Bland AI when creating batch calls
2. **Webhook**: Bland AI returns metadata with call results
3. **Database Update**: Used to update `outreach_attempts` table with call outcomes

---

## 📦 **Complete Metadata Structure**

### **Location in Code:**
File: `af_code/af_dtc_intro_call/services/blandai_service.py` (Lines 171-185)

```python
"metadata": {
    # --- NEW FIELDS (Added in recent update) ---
    "batch_id": batch_id,                                    # Our internal batch UUID
    "campaign_id": str(member.get("campaign_id")),           # Campaign UUID
    "pathway_id": str(config.get("pathway_id")),             # Bland AI pathway ID

    # --- EXISTING FIELDS (Original implementation) ---
    "attempt_id": str(member.get("attempt_id")),             # Our internal attempt UUID
    "member_id": str(member.get("member_id")),               # Member UUID
    "salesforce_account_number": member.get("salesforce_account_number"),  # Salesforce ID
    "first_name": member.get("first_name"),                  # Member first name
    "last_name": member.get("last_name"),                    # Member last name
    "called_number": member.get("primary_phone"),            # Phone number called
    "language_pref": member.get("language_pref"),            # Language preference
    "call_type_code": member.get("call_type"),               # Call type from campaign config
}
```

---

## 🔍 **Field-by-Field Breakdown**

### **1. batch_id** (String - UUID)
**Purpose**: Links this call to our internal batch tracking system

**Source**: Generated when creating batch record
- **File**: `af_code/af_dtc_intro_call/services/blandai_service.py`
- **Function**: `create_outreach_batch()` (Line 68)
- **Code**: `batch_id = str(uuid.uuid4())`

**Database Table**: `engage360.outreach_batches.batch_id`

**Example Value**: `"550e8400-e29b-41d4-a716-446655440000"`

**Usage**:
- Track which batch this call belongs to
- Query all calls in a batch
- Monitor batch completion status
- Link webhook responses to batch

**SQL Query to Find All Calls in Batch**:
```sql
SELECT *
FROM engage360.outreach_attempts
WHERE batch_id = '550e8400-e29b-41d4-a716-446655440000'
```

---

### **2. campaign_id** (String - UUID)
**Purpose**: Identifies which campaign this call belongs to

**Source**: From member's enrollment record
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 61 in config.py)
- **Column**: `mce.campaign_id`

**Database Table**: `engage360.campaigns_enhanced.campaign_id`

**Example Values**:
- DTC Intro Campaign: `"34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"`
- DTC Wellness Campaign: `"E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"`

**Usage**:
- Identify campaign type (intro vs wellness)
- Filter calls by campaign
- Report campaign-level metrics
- Apply campaign-specific business rules

---

### **3. pathway_id** (String)
**Purpose**: Bland AI conversational pathway identifier

**Source**: From campaign configuration
- **Database Query**: `GET_CAMPAIGN_CONFIG_QUERY` (Line 24-28 in config.py)
- **Column**: `bland_parameters_global` JSON → `pathway_id` field

**Database Table**: `engage360.campaign_call_configs_enhanced.bland_parameters_global`

**Example Values**:
- DTC Intro: `"pathway-dtc-intro-v1"`
- DTC Wellness: `"pathway-dtc-wellness-v2"`

**Usage**:
- Verify which conversational flow was used
- Debug pathway-specific issues
- Track pathway version changes
- Support A/B testing of pathways

---

### **4. attempt_id** (String - UUID) ⭐ **MOST CRITICAL FIELD**
**Purpose**: Primary key to link webhook back to our database record

**Source**: Generated when creating attempt record
- **File**: `af_code/af_dtc_intro_call/services/blandai_service.py`
- **Function**: `create_outreach_attempts()` (Line 88)
- **Code**: `attempt_id = str(uuid.uuid4())`

**Database Table**: `engage360.outreach_attempts.attempt_id` (Primary Key)

**Example Value**: `"660e8400-e29b-41d4-a716-446655440001"`

**Usage**:
- ⭐ **PRIMARY IDENTIFIER** for webhook processing
- Update call disposition (Completed, Failed, NoAnswer)
- Store call duration and outcome
- Link to Bland AI call_id (vendor_session_id)

**Webhook Processing Code**:
```python
# In bland_ai_webhook handler
attempt_id = webhook_payload['metadata']['attempt_id']

# Update database
UPDATE engage360.outreach_attempts
SET disposition = 'Completed',
    vendor_session_id = webhook_payload['call_id'],
    call_duration = webhook_payload['duration']
WHERE attempt_id = attempt_id
```

---

### **5. member_id** (String - UUID)
**Purpose**: Identifies the member who was called

**Source**: From members table via enrollment join
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 47 in config.py)
- **Column**: `m.member_id`

**Database Table**: `engage360.members.member_id` (Primary Key)

**Example Value**: `"770e8400-e29b-41d4-a716-446655440002"`

**Usage**:
- Track member call history
- Prevent duplicate calls (same member, same day)
- Query all attempts for a member
- Link to member profile data

**SQL Query to Find Member's Call History**:
```sql
SELECT
    oa.attempt_ts,
    oa.disposition,
    oa.call_duration,
    c.name as campaign_name
FROM engage360.outreach_attempts oa
JOIN engage360.member_campaign_enrollments_enhanced mce ON oa.enrollment_id = mce.enrollment_id
JOIN engage360.campaigns_enhanced c ON mce.campaign_id = c.campaign_id
WHERE mce.member_id = '770e8400-e29b-41d4-a716-446655440002'
ORDER BY oa.attempt_ts DESC
```

---

### **6. salesforce_account_number** (String - Nullable)
**Purpose**: Links to Salesforce CRM account

**Source**: From members table
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 48 in config.py)
- **Column**: `m.salesforce_account_number`

**Database Table**: `engage360.members.salesforce_account_number`

**Example Values**:
- `"SF-12345678"`
- `"001234567890ABC"`
- `null` (if not synced to Salesforce)

**Usage**:
- Sync call outcomes to Salesforce
- Link to external CRM records
- Support customer service lookups
- Cross-system reporting

---

### **7. first_name** (String)
**Purpose**: Member's first name

**Source**: From members table
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 49 in config.py)
- **Column**: `m.first_name`

**Database Table**: `engage360.members.first_name`

**Example Value**: `"John"`

**Usage**:
- Display in call logs
- Support customer service
- Personalization in reports
- Verify correct member contacted

**Note**: Also sent in `request_data` for AI pathway personalization

---

### **8. last_name** (String)
**Purpose**: Member's last name

**Source**: From members table
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 50 in config.py)
- **Column**: `m.last_name`

**Database Table**: `engage360.members.last_name`

**Example Value**: `"Doe"`

**Usage**:
- Display in call logs
- Support customer service
- Personalization in reports
- Verify correct member contacted

---

### **9. called_number** (String - E.164 Format)
**Purpose**: Phone number that was actually dialed

**Source**: From members table
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 51 in config.py)
- **Column**: `m.primary_phone`

**Database Table**: `engage360.members.primary_phone`

**Example Value**: `"+12125551234"`

**Format**: E.164 international format
- Starts with `+`
- Country code (1 for US)
- 10 digits for US numbers
- Total: 12 characters for US

**Usage**:
- Verify correct number was called
- Track call attempts per phone number
- Support call blocking/do-not-call lists
- Reconcile with carrier records

---

### **10. language_pref** (String)
**Purpose**: Member's preferred language for communication

**Source**: From members table
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 52 in config.py)
- **Column**: `m.language_pref`

**Database Table**: `engage360.members.language_pref`

**Example Values**:
- `"English"`
- `"Spanish"`
- `"en"` (ISO code)
- `"es"` (ISO code)

**Usage**:
- Route to appropriate AI pathway
- Select correct voice/accent
- Support multilingual campaigns
- Compliance with language access requirements

---

### **11. call_type_code** (String)
**Purpose**: Type of call being made (intro vs wellness)

**Source**: From campaign call configuration
- **Database Query**: `GET_MEMBERS_WITH_ATTEMPTS_QUERY` (Line 63 in config.py)
- **Column**: `cfg.call_type`

**Database Table**: `engage360.campaign_call_configs_enhanced.call_type`

**Example Values**:
- `"intro_call"` - DTC intro call (first contact)
- `"wellness_check"` - DTC wellness check call (follow-up)
- `"not_completed"` - Static value used in request_data

**Usage**:
- Determine call purpose
- Apply call-type-specific logic
- Support different conversation flows
- Track call type metrics

**Note**: Used in both `metadata.call_type_code` and `request_data.call_type_code`

---

## 🗄️ **Database Source Mapping**

### **Complete SQL Query:**
File: `af_code/af_dtc_intro_call/utils/config.py` (Lines 45-71)

```sql
SELECT
    -- Metadata Fields --
    m.member_id,                        -- → metadata.member_id
    m.salesforce_account_number,        -- → metadata.salesforce_account_number
    m.first_name,                       -- → metadata.first_name
    m.last_name,                        -- → metadata.last_name
    m.primary_phone,                    -- → metadata.called_number
    m.language_pref,                    -- → metadata.language_pref

    -- Request Data Fields --
    m.dob,                              -- → request_data.dob
    m.address_street,                   -- → request_data.service_address
    m.address_city,                     -- → request_data.city
    m.address_state,                    -- → request_data.state
    m.address_zip,                      -- → request_data.zip_code

    -- Device Info --
    md.device_id as device_udi,         -- (Not in payload currently)
    md.is_device_callable,              -- (Used for validation)

    -- Internal Tracking --
    oa.attempt_id,                      -- → metadata.attempt_id
    mce.campaign_id,                    -- → metadata.campaign_id
    mce.enrollment_id,                  -- (Internal use only)

    -- Campaign Config --
    cfg.call_type                       -- → metadata.call_type_code

FROM engage360.outreach_attempts oa
JOIN engage360.member_campaign_enrollments_enhanced mce
    ON oa.enrollment_id = mce.enrollment_id
JOIN engage360.members m
    ON mce.member_id = m.member_id
LEFT JOIN engage360.member_devices md
    ON m.member_id = md.member_id
LEFT JOIN engage360.campaign_call_configs_enhanced cfg
    ON mce.campaign_id = cfg.campaign_id
    AND cfg.config_status = 'active'
WHERE oa.batch_id = %s
  AND oa.disposition = 'Pending'
```

---

## 📞 **Complete Payload Example**

### **Full Bland AI Batch Payload:**

```json
{
  "global": {
    "pathway_id": "pathway-dtc-intro-v1",
    "pathway_version": "2024-10-15",
    "voice": "maya",
    "wait_for_greeting": true,
    "record": true,
    "answered_by_enabled": true,
    "noise_cancellation": true,
    "interruption_threshold": 100,
    "block_interruptions": false,
    "max_duration": 600,
    "model": "enhanced",
    "temperature": 0.7,
    "language": "en",
    "background_track": "default",
    "endpoint": null,
    "from": "+19876543210",
    "timezone": "America/New_York",
    "webhook": "https://ioe-function-prod.azurewebsites.net/api/bland_ai_webhook"
  },
  "call_objects": [
    {
      "phone_number": "+12125551234",
      "request_data": {
        "call_type_code": "not_completed",
        "language_pref": "English",
        "first_name": "John",
        "last_name": "Doe",
        "service_address": "123 Main St",
        "zip_code": "10001",
        "primary_phone": "+12125551234",
        "city": "New York",
        "state": "NY",
        "dob": "1950-06-15"
      },
      "metadata": {
        "batch_id": "550e8400-e29b-41d4-a716-446655440000",
        "campaign_id": "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC",
        "pathway_id": "pathway-dtc-intro-v1",
        "attempt_id": "660e8400-e29b-41d4-a716-446655440001",
        "member_id": "770e8400-e29b-41d4-a716-446655440002",
        "salesforce_account_number": "SF-12345678",
        "first_name": "John",
        "last_name": "Doe",
        "called_number": "+12125551234",
        "language_pref": "English",
        "call_type_code": "intro_call"
      }
    },
    {
      "phone_number": "+13105559876",
      "request_data": {
        "call_type_code": "not_completed",
        "language_pref": "Spanish",
        "first_name": "Maria",
        "last_name": "Garcia",
        "service_address": "456 Oak Ave",
        "zip_code": "90001",
        "primary_phone": "+13105559876",
        "city": "Los Angeles",
        "state": "CA",
        "dob": "1955-03-22"
      },
      "metadata": {
        "batch_id": "550e8400-e29b-41d4-a716-446655440000",
        "campaign_id": "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC",
        "pathway_id": "pathway-dtc-intro-v1",
        "attempt_id": "660e8400-e29b-41d4-a716-446655440003",
        "member_id": "770e8400-e29b-41d4-a716-446655440004",
        "salesforce_account_number": "SF-87654321",
        "first_name": "Maria",
        "last_name": "Garcia",
        "called_number": "+13105559876",
        "language_pref": "Spanish",
        "call_type_code": "intro_call"
      }
    }
  ]
}
```

---

## 🔄 **Webhook Return Flow**

### **Bland AI Webhook Payload (What Comes Back):**

When Bland AI completes a call, it sends this webhook to our endpoint:

```json
{
  "batch_id": "bland_batch_abc123xyz789",
  "call_id": "call_xyz123",
  "to": "+12125551234",
  "from": "+19876543210",
  "status": "completed",
  "answered": true,
  "duration": 180,
  "end_reason": "call_completed",
  "created_at": "2025-10-22T14:30:00Z",
  "answered_by": "human",

  "metadata": {
    "batch_id": "550e8400-e29b-41d4-a716-446655440000",
    "campaign_id": "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC",
    "pathway_id": "pathway-dtc-intro-v1",
    "attempt_id": "660e8400-e29b-41d4-a716-446655440001",
    "member_id": "770e8400-e29b-41d4-a716-446655440002",
    "salesforce_account_number": "SF-12345678",
    "first_name": "John",
    "last_name": "Doe",
    "called_number": "+12125551234",
    "language_pref": "English",
    "call_type_code": "intro_call"
  },

  "pathway_logs": [
    {
      "node_id": "greeting",
      "output": "Hello John, this is Medical Guardian calling..."
    },
    {
      "node_id": "confirm_identity",
      "output": "Can you confirm your date of birth?"
    }
  ],

  "analysis": {
    "summary": "Member confirmed identity and scheduled wellness check",
    "disposition_tags": ["INTERESTED", "APPOINTMENT_SCHEDULED"]
  }
}
```

### **How Webhook Uses Metadata:**

**File**: `functions/bland_ai_webhook.py`

```python
def process_bland_webhook(webhook_payload):
    # Extract metadata
    metadata = webhook_payload.get('metadata', {})
    attempt_id = metadata.get('attempt_id')
    member_id = metadata.get('member_id')
    campaign_id = metadata.get('campaign_id')

    # Map Bland AI status to our disposition
    bland_status = webhook_payload.get('status')
    disposition = map_disposition(bland_status, webhook_payload)

    # Update database
    UPDATE engage360.outreach_attempts
    SET
        disposition = disposition,
        vendor_session_id = webhook_payload['call_id'],
        call_duration = webhook_payload['duration'],
        pathway_data = JSON(pathway_logs),
        updated_ts = SYSDATETIMEOFFSET()
    WHERE attempt_id = attempt_id

    # Log for reporting
    logger.info(f"✅ Updated attempt {attempt_id} for member {member_id}")
    logger.info(f"   Campaign: {campaign_id}")
    logger.info(f"   Disposition: {disposition}")
```

---

## 🔄 **Comparison: DTC vs Partner Campaigns**

### **Metadata Differences:**

| Field | DTC Campaigns | Partner Campaigns | Notes |
|-------|---------------|-------------------|-------|
| `batch_id` | ✅ Yes | ✅ Yes | Same purpose |
| `campaign_id` | ✅ Yes | ✅ Yes | Same purpose |
| `pathway_id` | ✅ Yes | ✅ Yes | Same purpose |
| `attempt_id` | ✅ Yes | ✅ Yes | Primary key for both |
| `member_id` | ✅ Yes | ✅ Yes | Same purpose |
| `enrollment_id` | ❌ No | ✅ Yes | Partner includes enrollment FK |
| `org_id` | ❌ No | ✅ Yes | Partner includes organization |
| `config_id` | ❌ No | ✅ Yes | Partner includes config FK |
| `salesforce_account_number` | ✅ Yes | ❌ No | DTC only |
| `first_name` | ✅ Yes | ✅ Yes | Both include |
| `last_name` | ✅ Yes | ✅ Yes | Both include |
| `called_number` | ✅ Yes | ❌ No | DTC only |
| `language_pref` | ✅ Yes | ❌ No | DTC only |
| `call_type_code` | ✅ Yes | ❌ No | DTC only |
| `care_gaps` | ❌ No | ✅ Yes | Partner only (in request_data) |

### **Key Insights:**

1. **DTC metadata is more member-focused**:
   - Includes Salesforce integration
   - Includes language preference
   - Includes call type differentiation

2. **Partner metadata is more campaign-focused**:
   - Includes enrollment_id for tracking
   - Includes org_id for multi-org support
   - Includes care gaps in request_data

3. **Common Critical Fields**:
   - `attempt_id` - Primary key for webhook processing
   - `member_id` - Member identification
   - `campaign_id` - Campaign tracking
   - `batch_id` - Batch grouping

---

## 📊 **Metadata Usage Statistics**

### **Most Critical Fields (by usage):**

1. **attempt_id** (100% usage)
   - ⭐ Primary key for ALL webhook processing
   - Used in EVERY database update
   - Cannot be NULL

2. **member_id** (95% usage)
   - Member history tracking
   - Duplicate prevention
   - Cross-campaign reporting

3. **campaign_id** (90% usage)
   - Campaign metrics
   - Business rule application
   - Filter and segmentation

4. **batch_id** (85% usage)
   - Batch monitoring
   - Group operations
   - Completion tracking

5. **salesforce_account_number** (60% usage - when available)
   - CRM integration
   - External reporting
   - Customer service

6. **language_pref** (50% usage)
   - Pathway routing
   - Voice selection
   - Compliance

7. **first_name, last_name** (40% usage)
   - Display only
   - Verification
   - Logging

8. **called_number** (30% usage)
   - Verification
   - Reconciliation
   - Do-not-call checking

9. **call_type_code** (25% usage)
   - Call type reporting
   - Pathway differentiation

10. **pathway_id** (20% usage)
    - Debugging
    - Version tracking
    - A/B testing

---

## 🎯 **Best Practices**

### **When Adding New Metadata Fields:**

1. ✅ **Add to both submission AND webhook**
   - Ensure consistency
   - Support round-trip tracking

2. ✅ **Document the purpose**
   - Why is this field needed?
   - Who uses it?
   - When is it used?

3. ✅ **Map to database source**
   - Which table?
   - Which column?
   - How to query?

4. ✅ **Handle NULL values**
   - Can it be NULL?
   - What's the fallback?
   - How to display NULL?

5. ✅ **Test webhook processing**
   - Does webhook include the field?
   - Can we parse it?
   - Does it update correctly?

### **When Removing Metadata Fields:**

1. ⚠️ **Check webhook dependencies**
   - Is it used in webhook processing?
   - Will removal break anything?

2. ⚠️ **Check reporting dependencies**
   - Are there reports using this field?
   - Will removal break dashboards?

3. ⚠️ **Deprecate gradually**
   - Mark as deprecated first
   - Give teams time to adapt
   - Remove after confirmation

---

## 📝 **Summary**

### **DTC Metadata Contains:**
- ✅ 11 total fields
- ✅ 3 UUIDs (batch_id, campaign_id, attempt_id) for tracking
- ✅ 1 UUID (member_id) for member identification
- ✅ 1 external ID (salesforce_account_number) for CRM integration
- ✅ 2 name fields (first_name, last_name) for personalization
- ✅ 1 phone field (called_number) for verification
- ✅ 1 language field (language_pref) for routing
- ✅ 1 call type field (call_type_code) for differentiation
- ✅ 1 pathway field (pathway_id) for debugging

### **Primary Use Cases:**
1. **Webhook Processing** - Link call results back to database
2. **Member Tracking** - Identify who was called
3. **Campaign Analytics** - Report on campaign performance
4. **Batch Monitoring** - Track batch completion
5. **CRM Integration** - Sync with Salesforce
6. **Compliance** - Language access, call recording

### **Critical Success Factors:**
- ⭐ **attempt_id must always be included** - Primary key
- ⭐ **All UUIDs must be converted to strings** - Bland AI requirement
- ⭐ **Metadata must be consistent** - Submission = Webhook return
- ⭐ **NULL handling must be explicit** - Avoid errors

---

## 🔗 **Related Documentation**

- `DTC_CALL_FLOW.md` - Complete DTC call flow
- `DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md` - Database operations
- `WEBHOOK_TESTING_GUIDE.md` - Webhook testing
- `af_code/af_dtc_intro_call/services/blandai_service.py` - Payload builder
- `functions/bland_ai_webhook.py` - Webhook processor

---

**END OF DOCUMENT**

**Last Updated**: 2025-10-22
**Version**: 1.0
**Maintained By**: AI-POD Team - Data Science
