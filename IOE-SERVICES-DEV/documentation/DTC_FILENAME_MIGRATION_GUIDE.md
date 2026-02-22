# DTC Wellness CSV Filename Pattern Migration Guide

**Effective Date:** TBD (Pending deployment approval)
**BusinessCaseID:** BC-109 (DTC Wellness Campaign Processing)
**Owner:** AI-POD Team - Data Science

---

## Overview

This guide documents the migration from CamelCase to snake_case filename pattern for DTC Wellness CSV files.

**Migration Strategy:** 2-phase rollout with dual support period to allow upstream systems (Salesforce) to transition gracefully.

---

## Pattern Changes

### Old vs New Pattern Comparison

| Aspect | Old Pattern (LEGACY) | New Pattern (Preferred) |
|--------|---------------------|-------------------------|
| **Format** | `MedicalGuardian_DTCWellness_YYYYMMDD_Delta.csv` | `medical_guardian_dtc_wellness_YYYYMMDD.csv` |
| **Case** | CamelCase | snake_case (all lowercase) |
| **Suffix** | `_Delta.csv` | `.csv` |
| **Date Format** | YYYYMMDD (8 digits) | YYYYMMDD (8 digits) |
| **Example** | `MedicalGuardian_DTCWellness_20260202_Delta.csv` | `medical_guardian_dtc_wellness_20260202.csv` |

### Date Validation Rules

Both patterns enforce strict calendar date validation:

- **YYYY:** 4-digit year (e.g., 2026)
- **MM:** 2-digit month (01-12)
- **DD:** 2-digit day (01-31, validated for specific month/year)

**Invalid dates are REJECTED:**
- ❌ `20260230` - February 30 (invalid)
- ❌ `20260431` - April 31 (invalid)
- ❌ `20261340` - Month 13 (invalid)
- ❌ `20260229` - Feb 29 in non-leap year (invalid)
- ✅ `20240229` - Feb 29 in leap year (valid - 2024 is leap year)

---

## Migration Timeline

### Phase 1: Dual Support Period (2 weeks)

**Status:** Both patterns accepted

**Configuration:**
- `allow_legacy=True` in validator calls
- Both OLD and NEW patterns process successfully
- LEGACY pattern triggers deprecation warnings in logs

**When:**
- **Start:** Deployment date (TBD)
- **Duration:** 2 weeks minimum
- **End:** After upstream systems confirm transition complete

**Action Required:**
- Upstream systems (Salesforce) update export configuration to generate NEW pattern
- Monitor Application Insights logs for LEGACY pattern usage percentage
- Coordinate with Salesforce team on transition progress

**Success Criteria:**
- Both patterns process without errors
- LEGACY usage drops below 1% by end of Week 5
- Upstream systems confirm readiness for Phase 2

---

### Phase 2: New Pattern Only (Week 3+)

**Status:** Only NEW pattern accepted

**Configuration:**
- `allow_legacy=False` in validator calls
- Only NEW pattern accepted
- LEGACY pattern rejected with clear error message

**When:**
- **Start:** After 2-week dual support + upstream confirmation
- **Permanent:** Once deployed, LEGACY pattern will not be re-enabled

**Action Required:**
- Update code: Change `allow_legacy=True` to `allow_legacy=False` in:
  - `functions/dtc_file_processor.py` (line 25)
  - `af_code/af_dtc_logic.py` (line 2611)

**Success Criteria:**
- NEW pattern processes successfully
- LEGACY pattern rejected with helpful error message
- Zero production incidents for 48 hours

---

## Implementation Checklist

### For Development Team (AI-POD)

**Pre-Deployment:**
- [x] Create validator function (`af_code/shared/filename_validators.py`)
- [x] Update Azure Function trigger (`functions/dtc_file_processor.py`)
- [x] Update business logic (`af_code/af_dtc_logic.py`)
- [x] Create unit tests (33 tests, 100% pass rate)
- [ ] Update documentation files (see Documentation Updates section)
- [ ] Run code quality checks (black, ruff, mypy, bandit, pytest)
- [ ] Code review (2+ reviewers)
- [ ] QA sign-off on test plan

**Phase 1 Deployment:**
- [ ] Deploy to development environment
- [ ] Test with both NEW and LEGACY patterns
- [ ] Deploy to staging environment
- [ ] End-to-end testing with Salesforce staging
- [ ] Deploy to production
- [ ] Monitor Application Insights for 24 hours

**Phase 1 Monitoring (2 weeks):**
- [ ] Daily check: LEGACY pattern usage percentage
- [ ] Weekly sync with Salesforce team on transition progress
- [ ] Track errors related to filename validation
- [ ] Confirm upstream systems generating NEW pattern

**Phase 2 Deployment:**
- [ ] Update code: Set `allow_legacy=False`
- [ ] Deploy to development and test
- [ ] Deploy to staging and verify LEGACY rejection
- [ ] Deploy to production
- [ ] Monitor for 48 hours - zero incidents expected

---

### For Upstream Systems (Salesforce Team)

**Before Phase 1 Deployment:**
- [ ] Review new filename pattern requirements
- [ ] Identify export configuration that generates DTC Wellness CSVs
- [ ] Plan configuration change timeline

**During Phase 1 (Dual Support Period):**
- [ ] Update Salesforce export configuration to generate NEW pattern
- [ ] Test exports in Salesforce sandbox environment
- [ ] Verify exports arrive in Azure blob storage with correct pattern
- [ ] Monitor IOE Azure Function logs for successful processing
- [ ] Confirm 100% of new exports use NEW pattern for 1 week

**Before Phase 2:**
- [ ] Confirm all production exports using NEW pattern
- [ ] Provide sign-off to AI-POD Team for Phase 2 deployment

**After Phase 2:**
- [ ] Verify LEGACY pattern is rejected (expected behavior)
- [ ] Monitor for any errors or failed file uploads

---

## Testing Procedures

### Development Environment Testing

**Upload test files to `fs-dtc/landing` blob container:**

1. **Valid NEW pattern:**
   ```
   medical_guardian_dtc_wellness_20260202.csv
   medical_guardian_dtc_wellness_20240229.csv (leap year)
   ```
   **Expected:** ✅ Processes successfully, no warnings

2. **Valid LEGACY pattern (Phase 1 only):**
   ```
   MedicalGuardian_DTCWellness_20260202_Delta.csv
   ```
   **Expected (Phase 1):** ✅ Processes with deprecation warning
   **Expected (Phase 2):** ❌ Rejected with clear error message

3. **Invalid patterns:**
   ```
   medical_guardian_dtc_wellness_20260230.csv (Feb 30)
   medical_guardian_dtc_wellness_20260229.csv (2026 not leap year)
   medical_guardian_dtc_wellness_20260431.csv (Apr 31)
   Medical_Guardian_DTC_Wellness_20260202.csv (wrong case)
   invalid_filename.csv (completely wrong)
   ```
   **Expected:** ❌ All rejected with descriptive error messages

**Verification Steps:**
1. Check Azure Function logs for expected warnings/errors
2. Query `engage360_stg.file_processing_log` table:
   ```sql
   SELECT TOP 10 source_filename, current_status, created_ts
   FROM engage360_stg.file_processing_log
   ORDER BY created_ts DESC
   ```
3. Verify files moved to `processed/` or `error/` folders in blob storage

---

### Staging Environment Testing

**End-to-End Test:**
1. Salesforce generates test CSV with NEW filename pattern
2. Upload to staging blob storage (`fs-dtc/landing`)
3. Azure Function processes file automatically (blob trigger)
4. Verify complete workflow:
   - File validation passes
   - Members enrolled in campaigns
   - Scheduling service queues calls
   - Bland AI receives batch submission
5. Check Application Insights logs for complete trace

---

## Rollback Procedures

### Immediate Rollback (< 1 hour, if critical issues)

**Scenario:** Critical production issue requiring immediate rollback

**Steps:**
1. Azure Portal → IOE-function → Deployment Center
2. Select previous deployment slot (before filename pattern change)
3. Click "Swap" to production
4. Verify rollback: Upload test file with OLD pattern
5. Notify stakeholders via email/Slack

**Validation:**
- Upload `MedicalGuardian_DTCWellness_20260202_Delta.csv` → Should process successfully
- Check Application Insights for rollback confirmation log entry

**Time Estimate:** 15-30 minutes

---

### Phase Extension (if upstream not ready)

**Scenario:** Salesforce team needs more time to transition

**Steps:**
1. Extend Phase 1 dual support period by 1-2 weeks
2. Update this migration guide with new Phase 2 date
3. Schedule coordination meeting with Salesforce team
4. Identify and resolve blockers

**No code changes required** - Phase 1 code already supports both patterns

---

## Monitoring & Alerts

### Application Insights Queries

**Monitor LEGACY pattern usage:**
```kusto
traces
| where message contains "LEGACY pattern detected"
| where timestamp > ago(24h)
| summarize count() by bin(timestamp, 1h)
| render timechart
```

**Monitor filename validation errors:**
```kusto
traces
| where message contains "File skipped due to invalid naming"
| where timestamp > ago(24h)
| project timestamp, message
| order by timestamp desc
```

**Monitor processing success rate:**
```kusto
traces
| where message contains "File processing complete" or message contains "File processing failed"
| where timestamp > ago(24h)
| summarize SuccessCount = countif(message contains "complete"),
            FailureCount = countif(message contains "failed")
| extend SuccessRate = round(100.0 * SuccessCount / (SuccessCount + FailureCount), 2)
```

---

## Expected Log Messages

### Phase 1: NEW Pattern

```
🟡 New file detected: medical_guardian_dtc_wellness_20260202.csv
✅ [VALIDATOR] DTC Wellness - NEW pattern validated: 20260202
✅ NEW pattern validated: medical_guardian_dtc_wellness_20260202.csv (date: 20260202)
✅ Processing NEW pattern: medical_guardian_dtc_wellness_20260202.csv (date: 20260202)
✅ File processing complete.
```

### Phase 1: LEGACY Pattern

```
🟡 New file detected: MedicalGuardian_DTCWellness_20260202_Delta.csv
⚠️ [VALIDATOR] DTC Wellness - LEGACY pattern detected: 20260202
   This pattern will be deprecated soon. Use: medical_guardian_dtc_wellness_YYYYMMDD.csv
⚠️ LEGACY pattern detected: MedicalGuardian_DTCWellness_20260202_Delta.csv
   This pattern will be deprecated in 2 weeks
   Please update to: medical_guardian_dtc_wellness_YYYYMMDD.csv
⚠️ Processing LEGACY pattern: MedicalGuardian_DTCWellness_20260202_Delta.csv
   This pattern will be deprecated soon
   Please update to: medical_guardian_dtc_wellness_YYYYMMDD.csv
✅ File processing complete.
```

### Phase 1: Invalid Pattern

```
🟡 New file detected: medical_guardian_dtc_wellness_20260230.csv
❌ [VALIDATOR] DTC Wellness - Invalid date: 20260230 - day is out of range for month
⚠️ File skipped due to invalid naming: medical_guardian_dtc_wellness_20260230.csv
   Error: Invalid date in filename: 20260230 (day is out of range for month)
   Expected: medical_guardian_dtc_wellness_YYYYMMDD.csv
   Example: medical_guardian_dtc_wellness_20260202.csv
```

### Phase 2: LEGACY Pattern (Rejected)

```
🟡 New file detected: MedicalGuardian_DTCWellness_20260202_Delta.csv
❌ [VALIDATOR] DTC Wellness - Legacy pattern rejected: MedicalGuardian_DTCWellness_20260202_Delta.csv
⚠️ File skipped due to invalid naming: MedicalGuardian_DTCWellness_20260202_Delta.csv
   Error: Legacy pattern no longer accepted. Use: medical_guardian_dtc_wellness_YYYYMMDD.csv
   Expected: medical_guardian_dtc_wellness_YYYYMMDD.csv
   Example: medical_guardian_dtc_wellness_20260202.csv
```

---

## Documentation Updates

### Files Requiring Updates

**High Priority (4 files):**
- `README.md` - 4 occurrences (lines 188, 270, 278, 845)
- `IOE_AZURE_FUNCTIONS_COMPREHENSIVE_DOCUMENTATION.md` - 3 occurrences
- `summary.md` - 2 occurrences
- `CLAUDE.md` - 1 occurrence (line 688)

**Medium Priority (3 files):**
- `DTC_NAN_FIX_DEPLOYMENT_STEPS.md` - 3 occurrences
- `DTC_NAN_FIX_IMPLEMENTATION_SUMMARY.md` - 1 occurrence
- `documentation/AZURE_COMPONENTS_REFERENCE.md` - 2 occurrences

**Low Priority (1 file):**
- `.serena/memories/suggested_commands.md` - 2 occurrences

**Find & Replace:**
- OLD: `MedicalGuardian_DTCWellness_*_Delta.csv`
- NEW: `medical_guardian_dtc_wellness_YYYYMMDD.csv`

---

## Risk Assessment & Mitigation

### High Risk

**Risk:** Upstream system (Salesforce) not ready for new pattern by Phase 2
**Impact:** Files rejected, campaign processing halted
**Probability:** Medium
**Mitigation:**
- 2-week dual support period allows time for coordination
- Regular sync meetings with Salesforce team during Phase 1
- Phase extension option if needed (extend Phase 1 indefinitely)
- Clear communication of timeline expectations

**Rollback Plan:** Extend Phase 1 dual support, no code changes needed

---

### Medium Risk

**Risk:** Hidden filename dependencies in downstream processes
**Impact:** Unexpected failures in reporting or analytics
**Probability:** Low
**Mitigation:**
- Comprehensive code search completed - no filename parsing found
- Filename stored as-is in `file_processing_log.source_filename` (no parsing)
- Testing in staging environment before production

**Rollback Plan:** Revert to previous deployment slot (15 min rollback)

---

### Low Risk

**Risk:** Date validation too strict (edge cases not considered)
**Impact:** Valid files rejected incorrectly
**Probability:** Very Low
**Mitigation:**
- Python's `datetime.strptime()` is battle-tested for date validation
- Comprehensive test suite covers leap years, month boundaries, edge cases
- 33 unit tests with 100% pass rate

**Rollback Plan:** Not expected to be needed

---

## Contact Information

### Technical Support

**AI-POD Team - Data Science**
**Primary Contact:** [Your Team Email]
**Slack Channel:** #ai-pod-team

**Response Times:**
- **Critical (Production Down):** 2 hours
- **High Priority (File Rejection):** 4 hours
- **Standard (Questions):** 24 hours

---

### Upstream Systems Coordination

**Salesforce Team**
**Primary Contact:** [Salesforce Team Email]
**Slack Channel:** #salesforce-integration

---

## Appendix

### A. Code Locations

**Validator Function:**
- File: `af_code/shared/filename_validators.py`
- Function: `validate_dtc_wellness_filename()`
- Lines: 95-193

**Azure Function Trigger:**
- File: `functions/dtc_file_processor.py`
- Lines: 19-29 (validation logic)

**Business Logic:**
- File: `af_code/af_dtc_logic.py`
- Config: Line 184 (`expected_filename_pattern`)
- Validation: Lines 2608-2627
- File Type Detection: Lines 2663-2668

**Unit Tests:**
- File: `tests/test_dtc_filename_validation.py`
- Test Count: 33 tests
- Coverage: 100% of validator function

---

### B. Related Documentation

- `CSV_TESTING_GUIDE.md` - File processing testing procedures
- `DTC_CALL_FLOW.md` - DTC wellness campaign workflow
- `DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md` - Database operations
- `ENGAGE360_TABLE_USAGE_REFERENCE.md` - Database schema reference

---

### C. Database Impact

**No schema changes required.**

The `source_filename` column stores filenames as-is (VARCHAR):
- Table: `engage360_stg.file_processing_log`
- Column: `source_filename VARCHAR(500)`
- Impact: None - column already supports both patterns

**Query to verify filenames:**
```sql
SELECT
    source_filename,
    file_type,
    current_status,
    created_ts,
    CASE
        WHEN source_filename LIKE 'medical_guardian_dtc_wellness_%' THEN 'NEW'
        WHEN source_filename LIKE 'MedicalGuardian_DTCWellness_%_Delta.csv' THEN 'LEGACY'
        ELSE 'UNKNOWN'
    END AS pattern_type
FROM engage360_stg.file_processing_log
WHERE file_type = 'DTC_WELLNESS'
    AND created_ts >= DATEADD(day, -7, GETDATE())
ORDER BY created_ts DESC
```

---

**Last Updated:** 2026-02-03
**Version:** 1.0
**Status:** Draft (Pending deployment approval)
