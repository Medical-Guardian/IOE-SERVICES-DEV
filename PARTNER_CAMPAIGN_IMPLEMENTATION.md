# Partner Campaign Scheduler - Implementation Complete

## ✅ **Implementation Status: COMPLETE**

The Partner Campaign Scheduler has been fully implemented using existing database tables with minimal schema changes.

---

## 🗂️ **Files Created/Modified**

### **New Files Created:**
1. `af_code/functions/partner_campaign_scheduler.py` - Main timer function (30-min schedule)
2. `af_code/partner_campaign_scheduler/services/campaign_qualifier.py` - Campaign qualification logic
3. `af_code/partner_campaign_scheduler/services/member_eligibility.py` - Member eligibility with frequency checks
4. `af_code/partner_campaign_scheduler/services/batch_orchestrator.py` - Bland AI batch submission
5. `af_code/partner_campaign_scheduler/services/status_tracker.py` - Outreach tracking
6. `af_code/partner_campaign_scheduler/models/qualified_campaign.py` - Campaign model
7. `af_code/partner_campaign_scheduler/models/eligible_member.py` - Member model
8. `af_code/partner_campaign_scheduler/models/batch_request.py` - Batch models
9. `af_code/shared/bland_ai_client.py` - Bland AI API client
10. `database_schema_minimal.sql` - Database schema updates

### **Modified Files:**
1. `function_app.py` - Added Partner Campaign Scheduler registration

---

## 🗄️ **Database Schema Changes**

### **Required Changes (Minimal):**
```sql
-- Only one new column needed
ALTER TABLE ioe.campaigns_enhanced 
ADD audience_file_batch NVARCHAR(255);

-- Performance indexes
CREATE INDEX IX_campaigns_partner_active ON ioe.campaigns_enhanced(...);
CREATE INDEX IX_outreach_batches_campaign_submitted ON ioe.outreach_batches(...);
CREATE INDEX IX_member_devices_member_callable ON ioe.member_devices(...);
```

### **Existing Tables Used:**
- ✅ `ioe.campaigns_enhanced` (with new audience_file_batch column)
- ✅ `ioe.members` (using existing Channel, timezone, primary_phone)
- ✅ `ioe.member_devices` (using device_phone_number, is_device_callable)
- ✅ `ioe.member_campaign_enrollments_enhanced` (using enrollment_id FK)
- ✅ `ioe.outreach_batches` (for batch tracking)
- ✅ `ioe.outreach_attempts` (for individual call attempts)

---

## 🔧 **Key Features Implemented**

### **1. Campaign Qualification:**
- ✅ Active Partner campaigns detection
- ✅ Timezone-aware scheduling (member_tz vs operating_tz)
- ✅ Day of week filtering
- ✅ Operating hours validation
- ✅ Flexible scheduling validation (frequency_value + frequency_unit required)
- ✅ Auto contact preference conversion (auto → member_preference)

### **2. Member Eligibility:**
- ✅ Enrollment status filtering (ENROLLED only)
- ✅ Frequency-based eligibility (2 per week, etc.)
- ✅ Same-day duplicate prevention
- ✅ Timezone-aware member filtering
- ✅ Contact preference validation (phone, device, member_preference)
- ✅ Device callable verification

### **3. Contact Preference Logic:**
- ✅ `phone` → uses members.primary_phone
- ✅ `device` → uses member_devices.device_phone_number (if is_device_callable = 1)
- ✅ `auto` → converts to member_preference automatically
- ✅ `member_preference` → uses member's Channel field with fallback

### **4. Duplicate Prevention:**
- ✅ Triple protection against duplicate calls:
  1. Frequency checking (last attempt vs frequency rules)
  2. Same-day protection (no multiple attempts same day)
  3. Batch submission tracking (via outreach_batches table)

### **5. Batch Management:**
- ✅ 100 members per batch (configurable)
- ✅ Batch tracking in outreach_batches table
- ✅ Individual attempt tracking in outreach_attempts table
- ✅ Comprehensive logging and monitoring

---

## 🚀 **Deployment Steps**

### **1. Database Setup:**
```sql
-- Run this script in your SQL Server database
-- File: database_schema_minimal.sql
```

### **2. Environment Variables:**
Configure in Azure Function App Settings:
```
BLAND_AI_API_KEY=your_bland_ai_api_key
BLAND_AI_BASE_URL=https://api.bland.ai
BLAND_WEBHOOK_URL=https://your-function-app.azurewebsites.net/api/bland_ai_webhook
PARTNER_CAMPAIGN_PATHWAY_ID=your_partner_pathway_id
PARTNER_CAMPAIGN_VOICE_ID=your_partner_voice_id
BLAND_MAX_DURATION=300
```

### **3. Deploy Azure Function:**
```bash
# Deploy the updated function app
func azure functionapp publish your-function-app-name
```

### **4. Verify Deployment:**
- ✅ Check Azure Function logs for "Registering Partner Campaign Scheduler..."
- ✅ Verify timer trigger appears in Azure portal
- ✅ Monitor first execution (will run every 30 minutes)

---

## 🎯 **Real-World Campaign Examples**

### **Hamaspik Choice Campaign:**
```sql
-- Campaign Configuration
UPDATE ioe.campaigns_enhanced SET
    audience_file_batch = 'Hamaspik-FluQ4-20250923T0044',
    contact_pref = 'device',
    timezone_flag = 'member_tz',
    frequency_value = 2,
    frequency_unit = 'week'
WHERE name = 'Hamaspik_Flu_Q4-2025';
```

**Behavior:** 
- Calls device numbers only
- Each member called in their local timezone (9AM-5PM)
- Maximum 2 calls per week
- Only members from Hamaspik batch

### **FidelisCare Campaign:**
```sql
-- Campaign Configuration  
UPDATE ioe.campaigns_enhanced SET
    audience_file_batch = 'FidelisCare-FluQ4-20250925',
    contact_pref = 'member_preference',
    timezone_flag = 'operating_tz',
    operating_tz = 'EST',
    frequency_value = 2,
    frequency_unit = 'week'
WHERE name = 'Flu Outreach Q4-2025';
```

**Behavior:**
- Uses each member's contact preference
- All calls in EST timezone (4AM-12PM EST)
- Maximum 2 calls per week
- Only members from FidelisCare batch

---

## 📊 **Monitoring & Logging**

### **Key Log Messages to Monitor:**
```
🚀 [PARTNER-SCHEDULER] Timer triggered at...
📊 [CAMPAIGN-QUALIFIER] Found X qualified campaigns
👥 [MEMBER-ELIGIBILITY] Found X eligible members
📦 [BATCH-ORCHESTRATOR] Submitting batch of X members
✅ [STATUS-TRACKER] Created batch record with ID...
🎉 [PARTNER-SCHEDULER] EXECUTION COMPLETED SUCCESSFULLY
```

### **Performance Metrics:**
- **Execution frequency:** Every 30 minutes
- **Batch size:** Up to 100 members per batch
- **Processing time:** Expected < 2 minutes per execution
- **Database operations:** ~5-10 queries per campaign

---

## 🔍 **Troubleshooting**

### **Common Issues:**

1. **No campaigns found:**
   - Check campaign.status = 'Active'
   - Verify timezone_flag and operating hours
   - Check audience_file_batch is not null

2. **No members eligible:**
   - Verify member enrollment status = 'ENROLLED'
   - Check frequency rules (not called too recently)
   - Verify contact preferences and phone numbers

3. **Bland AI submission failed:**
   - Check API key configuration
   - Verify webhook URL is accessible
   - Check pathway_id and voice_id are valid

### **Debug Queries:**
```sql
-- Check active Partner campaigns
SELECT name, status, audience_file_batch, contact_pref, timezone_flag
FROM ioe.campaigns_enhanced 
WHERE campaign_type = 'Partner' AND status = 'Active';

-- Check recent batch submissions
SELECT ob.*, ce.name 
FROM ioe.outreach_batches ob
JOIN ioe.campaigns_enhanced ce ON ob.campaign_id = ce.campaign_id
WHERE ob.submitted_ts >= DATEADD(day, -1, SYSDATETIMEOFFSET())
ORDER BY ob.submitted_ts DESC;
```

---

## ✅ **Success Criteria**

The Partner Campaign Scheduler is working correctly when:
- ✅ Timer executes every 30 minutes without errors
- ✅ Active Partner campaigns are detected and processed
- ✅ Members are filtered correctly by timezone and frequency rules
- ✅ Batches are submitted to Bland AI successfully
- ✅ No duplicate calls occur within same day
- ✅ Webhook processing updates attempt records correctly

---

## 🎯 **Next Steps**

1. **Monitor first 24 hours** of operation
2. **Verify webhook processing** for completed calls
3. **Adjust frequency/batch size** if needed based on performance
4. **Add campaign-specific configurations** as requirements evolve

**Implementation Status: ✅ READY FOR PRODUCTION**