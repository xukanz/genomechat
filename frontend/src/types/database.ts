/**
 * Database-related types
 */

/**
 * Complexity level for example questions
 */
export type QuestionComplexity = 'basic' | 'medium' | 'advanced'

/**
 * An example question for a database
 */
export interface ExampleQuestion {
  label: string // Short theme for chip display
  text: string // Full query text
  complexity: QuestionComplexity
}

/**
 * Information about a database profile
 */
export interface DatabaseInfo {
  id: string
  name: string
  display_name: string
  database_type: string
  sql_dialect: string
  description: string
  domain: string
  is_active: boolean
  status: 'connected' | 'available'
  example_questions: ExampleQuestion[]
}

/**
 * Response from listing all databases
 */
export interface DatabaseListResponse {
  databases: DatabaseInfo[]
  active_database: string
}

/**
 * Response for getting/setting active database
 */
export interface ActiveDatabaseResponse {
  id: string
  name: string
  display_name: string
  database_type: string
  sql_dialect: string
  description: string
  domain: string
}

/**
 * Response from connecting to a database
 */
export interface ConnectDatabaseResponse {
  success: boolean
  database: DatabaseInfo
  message: string
}
