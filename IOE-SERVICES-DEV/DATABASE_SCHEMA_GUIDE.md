# Database Schema Reference Guide

## Overview

The project includes two comprehensive database schema reference files for the **engage360** schema in Azure SQL Database. These files provide complete documentation of all 64 tables used by the AI-IOE system.

## Schema Files Comparison

| Aspect | All_tables_schema.txt | Context Engage360 schema.txt |
|--------|----------------------|------------------------------|
| **File Path** | `documentation/All_tables_schema.txt` | `documentation/Context Engage360 schema.txt` |
| **Size** | 99 KB | 7.7 MB (78x larger) |
| **Lines** | 1,902 lines | 44,795 lines |
| **Tables Covered** | 64 tables (complete) | 43 tables (most important subset) |
| **Content** | Schema structure only | Schema + 5-10 sample data rows per table |
| **Sample Data** | None | CSV-formatted production-like examples |
| **Read Performance** | Fast (<1 second) | Slower (3-5 seconds) |
| **Grep Performance** | Instant | 1-2 seconds |
| **Primary Use** | Quick structure lookups | Understanding data formats and values |

## When to Use Each File

**Use `All_tables_schema.txt` (99 KB) for** (90% of cases):
- ✅ Finding column names and data types
- ✅ Checking table structure and relationships
- ✅ Verifying foreign key constraints
- ✅ Looking up index definitions
- ✅ Understanding primary key structure
- ✅ Fast grep searches for specific tables or columns

**Use `Context Engage360 schema.txt` (7.7 MB) for**:
- ✅ Seeing actual JSON structure in NVARCHAR(MAX) columns
- ✅ Understanding valid values for VARCHAR/status columns
- ✅ Viewing realistic foreign key relationships with example UUIDs
- ✅ Writing test data or mock data generators
- ✅ Debugging data format issues
- ✅ Learning typical data patterns and cardinality

## File Structure

**All_tables_schema.txt Format**:
```sql
CREATE TABLE [engage360].[table_name] (
    [column_name] DATA_TYPE CONSTRAINTS,
    ...
    CONSTRAINT [PK_name] PRIMARY KEY CLUSTERED ([column] ASC)
);
GO

ALTER TABLE [engage360].[table_name] WITH CHECK ADD
CONSTRAINT [FK_name] FOREIGN KEY([column])
REFERENCES [engage360].[other_table] ([column]);
GO

CREATE NONCLUSTERED INDEX [IX_name]
ON [engage360].[table_name] ([column] ASC);
GO

---------------- (separator between tables)
```

**Context Engage360 schema.txt Format**:
```sql
CREATE TABLE [engage360].[table_name] (...)
GO

ALTER TABLE ... (foreign keys)
GO

CREATE INDEX ... (indexes)
GO

---------------- (separator)
Sample Data of Table table_name
column1,column2,column3,...
"value1","value2","value3",...
"value1","value2","value3",...
(5-10 rows of CSV-formatted sample data)

---------------- (separator)
```

## Common Grep Patterns

**For All_tables_schema.txt** (structure lookups):
```bash
# Find complete table structure
grep -A 30 "CREATE TABLE \[engage360\]\.\[call_analysis_results\]" documentation/All_tables_schema.txt

# Find all foreign keys referencing a table
grep "REFERENCES \[engage360\]\.\[members\]" documentation/All_tables_schema.txt

# Find all tables with a specific column
grep "\[member_id\]" documentation/All_tables_schema.txt

# Find all indexes on a table
grep "ON \[engage360\]\.\[campaign_agent_executions\]" documentation/All_tables_schema.txt

# Find primary key definition
grep "PRIMARY KEY" documentation/All_tables_schema.txt | grep "table_name"
```

**For Context Engage360 schema.txt** (data examples):
```bash
# Find sample data for a table
grep -A 20 "Sample Data of Table call_analysis_results" "documentation/Context Engage360 schema.txt"

# Find examples of specific status values
grep "\"execution_status\"" "documentation/Context Engage360 schema.txt" | head -20

# Find JSON structure examples (agent_output, analysis_data)
grep -A 5 "agent_output" "documentation/Context Engage360 schema.txt" | head -50

# Find example UUIDs for foreign key relationships
grep -A 10 "Sample Data of Table action_execution_log" "documentation/Context Engage360 schema.txt"
```

## Key Tables by Category

**Call Analysis & AI** (18 tables):
- `call_analysis_results` - Complete analysis results with JSON columns
- `call_transcripts` - Raw transcripts from Bland AI
- `call_summaries` - Human-readable summaries for RAG indexing
- `ai_decisions` - Campaign agent decisions with reasoning
- `ai_execution_context` - Context passed to AI agents
- `agent_execution_log` - Individual agent execution tracking
- `sentiment_analysis`, `risk_stratification_findings`, `compliance_findings`
- `topic_analysis`, `intent_analysis`, `emotion_timeline`

**Campaign Management** (15 tables):
- `campaigns_enhanced` - Campaign definitions and configuration
- `campaign_policies` - Campaign rules and constraints
- `campaign_call_configs_enhanced` - Call script configuration
- `campaign_agent_executions` - Campaign agent execution history
- `member_campaign_enrollments_enhanced` - Member enrollment tracking
- `outreach_attempts` - SMS/call attempt history
- `outreach_batches` - Batch outreach processing

**Member & Organization** (8 tables):
- `members` - Member demographics and contact information
- `member_devices` - Device registration and metadata
- `member_identifiers` - Alternative identifiers (external IDs)
- `orgs` - Organization/customer configuration
- `care_gaps` - Identified care gaps for members

**Action Execution & Audit** (8 tables):
- `action_execution_log` - Automated action execution tracking
- `action_items` - Manual action items from analysis
- `executed_actions` - Legacy action tracking
- `tool_call_audit` - HIPAA-compliant audit log for all tool calls
- `attempt_audit_log` - Outreach attempt audit trail

**Communication Logs** (5 tables):
- `bland_call_logs` - Bland AI call metadata and status
- `bland_sms_communications` - SMS communication history
- `wellness_health_ratings` - Member wellness check-in responses

**System & Configuration** (10 tables):
- `analysis_templates` - Reusable analysis configurations
- `call_analysis_queue` - Processing queue with status tracking
- `summary_processing_queue` - RAG indexing queue
- `retry_policy` - Retry configuration for failures
- `system_locks` - Distributed lock management
- `error_log` - System error tracking
- `analytics_daily_snapshot` - Daily analytics aggregation

## Database Characteristics

**Schema**: `engage360` (all tables)
**Database**: Azure SQL Database with Transparent Data Encryption
**Primary Keys**: UUIDs (UNIQUEIDENTIFIER with DEFAULT newid())
**Timestamps**: DATETIMEOFFSET(7) for timezone-aware timestamps
**JSON Storage**: NVARCHAR(MAX) columns for complex data structures

## Integration with Code

**When Writing Database Code**:

1. **Check schema structure first**:
   ```bash
   grep -A 30 "CREATE TABLE \[engage360\]\.\[table_name\]" documentation/All_tables_schema.txt
   ```

2. **Use existing db_client.py methods** when available:
   - File: `af_code/CallAnalysisFunctionApp/shared_code/db_client.py`
   - Methods: `get_call_data()`, `store_analysis_results()`, `update_queue_status()`, etc.

3. **Check sample data for value formats** (if needed):
   ```bash
   grep -A 20 "Sample Data of Table table_name" "documentation/Context Engage360 schema.txt"
   ```

4. **Always use parameterized queries** (HIPAA requirement):
   ```python
   cursor.execute("SELECT * FROM engage360.calls WHERE call_id = %s", (call_id,))
   ```

5. **Validate with sql_validator.py**:
   - File: `af_code/CallAnalysisFunctionApp/shared_code/sql_validator.py`

## Performance Guidelines

**Decision Tree**:
```
Need database info?
├─ Need column names/types/constraints? → Use All_tables_schema.txt (fast)
├─ Need to understand JSON structure? → Use Context Engage360 schema.txt
├─ Need valid status/enum values? → Use Context Engage360 schema.txt
├─ Writing new query? → Start with All_tables_schema.txt
└─ Debugging data format? → Use Context Engage360 schema.txt
```

**Best Practices**:
- Always start with `All_tables_schema.txt` for structure
- Grep instead of reading full file when possible
- Use `-A` flag with grep to get context lines
- Reference db_client.py before writing new database code
- Never read entire `Context Engage360 schema.txt` unless necessary
