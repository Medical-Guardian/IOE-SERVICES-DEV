# Database Migration Instructions

## Gender Columns Migration (2025-11-10)

### Overview

The DTC file processor now supports an optional `member_gender` field in CSV uploads. Before processing CSV files with gender data, you must run the database migration script to add the required columns to the staging table.

**Important**: Production table (`engage360.members`) already has `gender CHAR(1)` column. This migration only adds columns to the staging table.

---

## Current Error

If you see this error when uploading DTC CSV files:

```
Invalid column name 'member_gender'
Invalid column name 'gender_clean'
```

This means the database tables have not been updated yet. Follow the migration steps below.

---

## Migration File

**Location**: `database/add_gender_columns_migration.sql`

**What it does**:
1. Verifies production table already has `gender CHAR(1)` column
2. Adds `member_gender VARCHAR(50) NULL` to `engage360_stg.stg_dtc_wellness_delta` (staging)
3. Adds `gender_clean CHAR(1) NULL` to `engage360_stg.stg_dtc_wellness_delta` (staging)
4. Verifies all columns were created successfully

**Data Type Note**: Uses `CHAR(1)` for `gender_clean` to match production table schema

---

## How to Run Migration

### Option 1: Azure Portal SQL Query Editor

1. Go to Azure Portal: https://portal.azure.com
2. Navigate to your SQL Database (IOE database)
3. Click **Query editor** in the left menu
4. Login with your database credentials
5. Copy the contents of `database/add_gender_columns_migration.sql`
6. Paste into the query window
7. Click **Run**
8. Verify output shows "✅ Added column" messages

### Option 2: SQL Server Management Studio (SSMS)

1. Open SSMS
2. Connect to your Azure SQL Server
3. Open `database/add_gender_columns_migration.sql`
4. Execute the script (F5)
5. Review the Messages tab for success confirmations

### Option 3: Azure Data Studio

1. Open Azure Data Studio
2. Connect to your Azure SQL Server
3. File → Open → Select `database/add_gender_columns_migration.sql`
4. Run the script
5. Check output for success messages

### Option 4: Command Line (sqlcmd)

```bash
# Login to Azure
az login

# Run migration script
sqlcmd -S your-server.database.windows.net -d your-database \
       -U your-username -P your-password \
       -i database/add_gender_columns_migration.sql
```

---

## Verification

After running the migration, verify the columns exist:

```sql
-- Check staging table
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_dtc_wellness_delta'
  AND COLUMN_NAME IN ('member_gender', 'gender_clean');

-- Check production table
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'members'
  AND COLUMN_NAME = 'gender';
```

**Expected Results**:
- `engage360_stg.stg_dtc_wellness_delta.member_gender`: VARCHAR(50), NULL
- `engage360_stg.stg_dtc_wellness_delta.gender_clean`: CHAR(1), NULL
- `engage360.members.gender`: CHAR(1), NULL (already exists)

---

## Testing After Migration

1. **Upload a test DTC CSV file** with the `member_gender` column:

```csv
org_id,salesforce_account_number,...,member_dob,member_gender,device_udi,...
ORG001,123456789,...,1965-03-15,M,UDI123,...
ORG001,987654321,...,1970-08-22,Female,UDI987,...
```

2. **Monitor Azure Function logs** for successful processing

3. **Verify data in database**:

```sql
-- Check staging data
SELECT TOP 5 member_gender, gender_clean
FROM engage360_stg.stg_dtc_wellness_delta
WHERE member_gender IS NOT NULL;

-- Check production data
SELECT TOP 5 member_id, first_name, last_name, gender
FROM engage360.members
WHERE gender IS NOT NULL;
```

---

## Gender Field Specifications

### Input Values (member_gender in CSV)

- **Male**: `M`, `Male`, `MALE`, `m`, `male`
- **Female**: `F`, `Female`, `FEMALE`, `f`, `female`
- **Other**: Any other non-empty value (stored as NULL)
- **Empty/Null**: Field can be completely omitted or empty

### Standardized Values (gender_clean / gender in DB)

- `M` (CHAR 1) - Male
- `F` (CHAR 1) - Female
- `NULL` - Not provided or other values

**IMPORTANT**: Production table uses `CHAR(1)` with constraint: `gender IN ('M', 'F', NULL)`
- Any "Other" values from CSV are mapped to NULL (not stored as 'O')
- Only M and F are allowed in the database

### Validation Rules

- Field is **completely optional** - no errors if missing
- Empty values are stored as NULL (not as empty string)
- Case-insensitive matching for M/Male/F/Female
- All other values (Other, Non-binary, etc.) mapped to NULL for database compatibility

**Code Reference**: `af_code/af_dtc_logic.py` lines 1289-1305

---

## Rollback (If Needed)

If you need to remove the gender columns from staging:

```sql
-- Remove from staging table only
ALTER TABLE engage360_stg.stg_dtc_wellness_delta DROP COLUMN member_gender;
ALTER TABLE engage360_stg.stg_dtc_wellness_delta DROP COLUMN gender_clean;

-- DO NOT remove from production (it's used by other systems)
-- ALTER TABLE engage360.members DROP COLUMN gender;  -- Don't run this!
```

**Warning**: This will permanently delete any gender data in the staging table. Production table gender column should NOT be removed.

---

## Related Documentation

- **CSV Testing Guide**: `CSV_TESTING_GUIDE.md` (updated with gender examples)
- **DTC Logic Code**: `af_code/af_dtc_logic.py` (CSV validation and processing)
- **Schema Guide**: `DATABASE_SCHEMA_GUIDE.md` (how to query schemas)
- **Table Reference**: `ENGAGE360_TABLE_USAGE_REFERENCE.md` (updated with gender field)

---

## Support

If you encounter issues:

1. **Check migration output** - Look for error messages in SQL execution results
2. **Verify permissions** - Ensure database user has ALTER TABLE permissions
3. **Check existing columns** - Use INFORMATION_SCHEMA queries above
4. **Contact**: AI-POD Team - Data Science at Medical Guardian

---

**Migration Created**: 2025-11-10
**Python Code Updated**: 2025-11-07
**Status**: Ready to deploy
