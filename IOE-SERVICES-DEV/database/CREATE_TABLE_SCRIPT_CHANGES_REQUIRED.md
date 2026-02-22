# CREATE TABLE Script Changes Required

**File**: `database/create_stg_device_activation_delta_table.sql`

**Date**: 2025-12-23

**Purpose**: Update staging table creation script to match Python code expectations

---

## Summary of Changes

**4 changes required**:
- ✅ ADD `address_country NVARCHAR(50),` after line 83 (after `zip` field)
- ✅ ADD `member_brand NVARCHAR(100),` after line 88 (after `language_pref` field)
- ❌ REMOVE `fall_detection_status_clean NVARCHAR(50),` at line ~119 (obsolete)
- ❌ REMOVE `battery_status_clean NVARCHAR(50),` at line ~120 (obsolete)

---

## Change 1: Add address_country Column

**Location**: After line 83 (in Member Address section)

### FIND THIS SECTION (Lines 79-88):

```sql
-- Member Address (combined from 5 CSV fields during validation)
service_address NVARCHAR(500),                         -- Combined: street, city, state zip
city NVARCHAR(100),                                    -- From member_address_city
state NVARCHAR(2),                                     -- From member_address_state
zip NVARCHAR(10),                                      -- From member_address_zip

-- Member Demographics
dob DATE,                                              -- Date of birth
timezone NVARCHAR(50),                                 -- Mapped to IANA format (America/New_York)
language_pref NVARCHAR(10),                            -- Mapped to EN/ES/Other
```

### REPLACE WITH:

```sql
-- Member Address (combined from 5 CSV fields during validation)
service_address NVARCHAR(500),                         -- Combined: street, city, state zip
city NVARCHAR(100),                                    -- From member_address_city
state NVARCHAR(2),                                     -- From member_address_state
zip NVARCHAR(10),                                      -- From member_address_zip
address_country NVARCHAR(50),                          -- Country code (US, CA, etc.)

-- Member Demographics
dob DATE,                                              -- Date of birth
timezone NVARCHAR(50),                                 -- Mapped to IANA format (America/New_York)
language_pref NVARCHAR(10),                            -- Mapped to EN/ES/Other
```

**What Changed**: Added `address_country NVARCHAR(50),` line after `zip` field

**Why**: Python code expects this column for storing country codes (defaults to "US")

---

## Change 2: Add member_brand Column

**Location**: After line 88 (in Member Demographics section)

### FIND THIS SECTION (Lines 86-92):

```sql
-- Member Demographics
dob DATE,                                              -- Date of birth
timezone NVARCHAR(50),                                 -- Mapped to IANA format (America/New_York)
language_pref NVARCHAR(10),                            -- Mapped to EN/ES/Other

-- Device Information
device_udi NVARCHAR(100),                              -- Device UDI/Serial Number (REQUIRED)
```

### REPLACE WITH:

```sql
-- Member Demographics
dob DATE,                                              -- Date of birth
timezone NVARCHAR(50),                                 -- Mapped to IANA format (America/New_York)
language_pref NVARCHAR(10),                            -- Mapped to EN/ES/Other
member_brand NVARCHAR(100),                            -- Member brand/plan (MedScope, MG State Pay, etc.)

-- Device Information
device_udi NVARCHAR(100),                              -- Device UDI/Serial Number (REQUIRED)
```

**What Changed**: Added `member_brand NVARCHAR(100),` line after `language_pref` field

**Why**: Python code expects this column for storing member brand/plan information from CSV

---

## Change 3: Remove fall_detection_status_clean Column

**Location**: Line ~119 (in Cleaned/Transformed Columns section)

### FIND THIS SECTION (Lines 117-121):

```sql
service_address_clean NVARCHAR(500),                   -- Combined from 5 address fields
brand_clean NVARCHAR(100),                             -- Cleaned brand value
fall_detection_status_clean NVARCHAR(50),              -- Converted from numeric (1/0 → Active/Inactive)
battery_status_clean NVARCHAR(50),                     -- Converted from mode (Standard → Good)
org_id UNIQUEIDENTIFIER,                               -- Looked up from partner_name
```

### REPLACE WITH:

```sql
service_address_clean NVARCHAR(500),                   -- Combined from 5 address fields
brand_clean NVARCHAR(100),                             -- Cleaned brand value
org_id UNIQUEIDENTIFIER,                               -- Looked up from partner_name
```

**What Changed**: Removed `fall_detection_status_clean NVARCHAR(50),` line

**Why**: This column is obsolete - old column name from previous code version. Python now uses `fall_detection_clean` instead.

---

## Change 4: Remove battery_status_clean Column

**Location**: Line ~120 (in Cleaned/Transformed Columns section)

**Note**: This is the same section as Change 3 - the line will already be removed if you applied Change 3 correctly.

**What Changed**: Removed `battery_status_clean NVARCHAR(50),` line

**Why**: This column is obsolete - old column name from previous code version. Python now uses `powersaver_mode_clean` instead.

---

## Verification After Changes

After making these changes, verify the script defines exactly **51 columns**:

- **7 metadata columns**: file_batch_id, row_number_in_file, uploaded_by_user, uploaded_ts, processing_status, validation_status, error_message
- **27 CSV source columns**: partner_name → unenrollment_reason (including new address_country and member_brand)
- **11 cleaned columns**: first_name_clean → org_id (excluding obsolete fall_detection_status_clean and battery_status_clean)
- **4 timestamp columns**: cleansing_started_ts, cleansing_completed_ts, enrollment_started_ts, enrollment_completed_ts
- **2 tracking columns**: member_id_processed, enrollment_id_processed

### Quick Check - Search for These:

```bash
# Should find 2 matches (1 comment in header, 1 actual column definition)
grep -n "address_country" database/create_stg_device_activation_delta_table.sql

# Should find 1 match (the actual column definition)
grep -n "member_brand" database/create_stg_device_activation_delta_table.sql

# Should find 0 matches (column removed)
grep -n "fall_detection_status_clean" database/create_stg_device_activation_delta_table.sql

# Should find 0 matches (column removed)
grep -n "battery_status_clean" database/create_stg_device_activation_delta_table.sql
```

---

## Why These Changes Are Safe

1. **address_country**: Nullable column, Python provides "US" default, production table ready
2. **member_brand**: Nullable column, Python provides fallback, production table ready
3. **fall_detection_status_clean**: Unused column, no code references, safe to remove
4. **battery_status_clean**: Unused column, no code references, safe to remove

---

## Impact on Documentation

After updating the CREATE TABLE script, also update line 189 in the script's comments:

### FIND:
```sql
PRINT '   Columns: 51 total (7 metadata + 27 CSV + 11 cleaned + 4 timestamps + 2 tracking)'
```

### KEEP AS IS:
This is already correct - we're changing from 53 to 51 columns by adding 2 and removing 2.

**Before changes**: Had 53 columns (34 source + 13 cleaned + rest)
**After changes**: Has 51 columns (36 source + 9 cleaned + rest) ✅

---

## Testing After Changes

After updating the script, if you need to recreate the table:

1. **Backup existing data** (if any):
   ```sql
   SELECT * INTO engage360_stg.stg_device_activation_delta_backup
   FROM engage360_stg.stg_device_activation_delta;
   ```

2. **Drop existing table**:
   ```sql
   DROP TABLE engage360_stg.stg_device_activation_delta;
   ```

3. **Run updated CREATE TABLE script**:
   ```sql
   -- Run the updated create_stg_device_activation_delta_table.sql
   ```

4. **Verify column count**:
   ```sql
   SELECT COUNT(*) AS total_columns
   FROM INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_SCHEMA = 'engage360_stg'
     AND TABLE_NAME = 'stg_device_activation_delta';
   -- Should return: 51
   ```

5. **Restore backup data** (if needed):
   ```sql
   INSERT INTO engage360_stg.stg_device_activation_delta
   SELECT * FROM engage360_stg.stg_device_activation_delta_backup;
   ```

---

## Files Modified

- ✅ `database/create_stg_device_activation_delta_table.sql` - **YOU WILL UPDATE THIS**
- ✅ `database/fix_device_activation_staging_table_schema.sql` - **MIGRATION SCRIPT (ALREADY CREATED)**
- ✅ `database/CREATE_TABLE_SCRIPT_CHANGES_REQUIRED.md` - **THIS DOCUMENT**

---

## Status

- ✅ **Migration script created**: `database/fix_device_activation_staging_table_schema.sql` (run this FIRST to fix immediate error)
- ⏳ **CREATE TABLE script**: `database/create_stg_device_activation_delta_table.sql` (update this for future table recreations)
- ⏳ **Testing**: Upload CSV file after migration completes

---

**Last Updated**: 2025-12-23
**BusinessCaseID**: BC-TBD (Device Activation System)
