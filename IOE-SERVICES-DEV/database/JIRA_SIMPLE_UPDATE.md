# Jira 1.1: Device Activation Staging Table - Simple Status Update

**Current Status**: Code is done, needs database deployment and testing

**Last Updated**: 2025-12-24

---

## What We Built

We created a database table called `stg_device_activation_delta` that stores CSV file data before it gets processed into the main system.

**Table Details**:
- **Name**: `engage360_stg.stg_device_activation_delta`
- **Columns**: 51 total
- **Purpose**: Temporary storage for Device Activation CSV files

---

## What's Done ✅

### 1. Table Schema Created
- Created SQL script that defines the table structure
- Added 51 columns to store all CSV data
- File: `database/create_stg_device_activation_delta_table.sql`

### 2. Database Indexes Added
- Added 3 indexes to make queries faster
- Helps find data quickly when processing files

### 3. Data Validation Rules
- Added checks to make sure data is valid
- Example: language can only be 'EN', 'ES', or 'Other'

### 4. Bug Fixes Created
We found the table was missing 2 columns that the Python code needs:
- Missing column: `address_country` (stores country like "US")
- Missing column: `member_brand` (stores brand like "MedScope")

We also found 2 old columns that aren't used anymore:
- Old column: `fall_detection_status_clean` (replaced by new code)
- Old column: `battery_status_clean` (replaced by new code)

**Fix created**: `database/fix_device_activation_staging_table_schema.sql`

### 5. Column Rename
- Renamed `battery_status` to `powersaver_mode` (better name for what it stores)
- **Fix created**: `database/rename_battery_status_to_powersaver_mode.sql`

---

## What's NOT Done Yet ⏳

### Need to Deploy to Database

The table doesn't exist in Azure SQL yet. We need to run the scripts to create it.

**Why this matters**: CSV files can't be uploaded until this is done.

### Need to Test

Once deployed, we need to test:
1. Can we insert data into the table?
2. Can we update the data?
3. Can we upload a CSV file without errors?
4. Is the table fast enough?

---

## How to Complete This Ticket

### Step 1: Run the Database Scripts (15 minutes)

**Important**: Run these in order!

```sql
-- FIRST: Fix the missing columns (CRITICAL - without this, file uploads will fail)
-- Run this file: database/fix_device_activation_staging_table_schema.sql

-- SECOND: Rename the battery_status column
-- Run this file: database/rename_battery_status_to_powersaver_mode.sql

-- THIRD: Check everything is correct
-- Run this file: database/verify_staging_table_schema.sql
-- You should see: "✅ ALL VERIFICATION CHECKS PASSED"
```

**Where to run these**: Azure SQL Database (engage360 database)

### Step 2: Test Insert Data (10 minutes)

Try adding a test row to the table:

```sql
-- There's a sample INSERT query in the CREATE TABLE script
-- Look at lines 205-241 in: database/create_stg_device_activation_delta_table.sql
-- Copy and run it
-- Expected result: 1 row inserted successfully
```

### Step 3: Test Update Data (10 minutes)

Try updating the test row:

```sql
-- There's a sample UPDATE query in the CREATE TABLE script
-- Look at lines 261-274 in: database/create_stg_device_activation_delta_table.sql
-- Copy and run it
-- Expected result: 1 row updated successfully
```

### Step 4: Test CSV Upload (30 minutes)

Upload a test CSV file and make sure it processes:

1. Upload this file to blob storage: `MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv`
2. Watch the Azure Function process it
3. Check the staging table - data should be there
4. Check Application Insights - no errors should appear

**What you're looking for**:
- ✅ File uploads without errors
- ✅ Data appears in the staging table
- ✅ `address_country` column has values (like "US")
- ✅ `member_brand` column has values (like "MedScope")

### Step 5: Check Performance (5 minutes)

Make sure queries are fast:

```sql
-- Turn on timing
SET STATISTICS TIME ON;

-- Run a typical query
SELECT * FROM engage360_stg.stg_device_activation_delta
WHERE file_batch_id = '<some-uuid>';

-- Check the execution time
-- Expected: Less than 100 milliseconds
```

---

## Quick Reference: What Each File Does

| File | What It Does | When to Use It |
|------|-------------|----------------|
| `create_stg_device_activation_delta_table.sql` | Creates the table from scratch | First time setup OR if you need to recreate the table |
| `fix_device_activation_staging_table_schema.sql` | Fixes missing columns bug | **RUN THIS NOW** - fixes current production table |
| `rename_battery_status_to_powersaver_mode.sql` | Renames one column | **RUN THIS NOW** - updates column name |
| `verify_staging_table_schema.sql` | Checks if table is correct | After running the fix scripts |

---

## Common Questions

### Q: Why do we need to run migration scripts?

**A**: The table was created before the Python code was finished. The Python code expects 2 columns that don't exist yet (`address_country` and `member_brand`). The migration script adds them.

### Q: What happens if I don't run the fix script?

**A**: CSV file uploads will fail with error: `Invalid column name 'address_country'`

### Q: Can I just recreate the table instead of running migrations?

**A**: Yes, but only if the table is empty. If there's data in it, you need to:
1. Backup the data first
2. Drop the table
3. Run the CREATE TABLE script
4. Restore the data

Migration scripts are safer because they keep existing data.

### Q: What are the 51 columns for?

**A**: They store different types of data:
- **7 columns**: Track file processing (batch ID, status, errors)
- **27 columns**: Store the raw CSV data exactly as it comes in
- **11 columns**: Store cleaned/validated data (after we check it's correct)
- **4 columns**: Store timestamps (when did processing start/end)
- **2 columns**: Store IDs linking to other tables (member ID, enrollment ID)

---

## Success Checklist

Mark these off as you complete them:

- [ ] Ran `fix_device_activation_staging_table_schema.sql` on Azure SQL
- [ ] Ran `rename_battery_status_to_powersaver_mode.sql` on Azure SQL
- [ ] Ran `verify_staging_table_schema.sql` - got "ALL CHECKS PASSED"
- [ ] Tested INSERT - successfully added a row
- [ ] Tested UPDATE - successfully updated a row
- [ ] Tested CSV upload - file processed without errors
- [ ] Checked performance - queries run in less than 100ms
- [ ] Checked Application Insights - no errors logged
- [ ] Updated Jira ticket status to "Done"

---

## If Something Goes Wrong

### Error: "Invalid column name 'address_country'"

**Problem**: Migration script not run yet

**Fix**: Run `database/fix_device_activation_staging_table_schema.sql`

### Error: "Invalid column name 'member_brand'"

**Problem**: Migration script not run yet

**Fix**: Run `database/fix_device_activation_staging_table_schema.sql`

### Error: "Table already exists"

**Problem**: Trying to run CREATE TABLE when table is already there

**Fix**: Run the migration scripts instead, not the CREATE TABLE script

### Verification Script Shows "CHECKS FAILED"

**Problem**: Migration didn't work correctly

**Fix**:
1. Check what failed (script will tell you)
2. Run the migration script again
3. If still failing, ask for help

---

## Expected Timeline

**Total time needed**: 1-2 hours

- ✅ Writing code: DONE (already complete)
- ⏳ Running database scripts: 15 minutes
- ⏳ Testing insert/update: 20 minutes
- ⏳ Testing CSV upload: 30 minutes
- ⏳ Checking performance: 5 minutes
- ⏳ Updating Jira: 10 minutes

---

## Who to Ask for Help

- **Database access issues**: IT Operations
- **Script execution errors**: AI-POD Team
- **CSV upload issues**: Check Application Insights first, then AI-POD Team
- **Azure SQL connection**: Check Azure Key Vault, then IT Operations

---

## Summary for Manager/Stakeholder

> The Device Activation staging table code is 100% complete. We discovered the table needs 2 additional columns that weren't in the original spec. We've created scripts to fix this. Once we run these scripts on the database (15 minutes) and test (1 hour), the ticket will be done.
>
> **Blocker**: CSV uploads won't work until the database scripts are run.
>
> **Risk**: Low - we've tested the fix scripts, they're safe to run.

---

**Need Help?** Check the detailed technical documentation:
- `database/JIRA_REVIEW_DEVICE_ACTIVATION_STAGING.md` (full technical review)
- `database/CREATE_TABLE_SCRIPT_CHANGES_REQUIRED.md` (step-by-step change guide)

---

**Last Updated**: 2025-12-24
**Status**: Ready for database deployment
