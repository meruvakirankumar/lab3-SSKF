# Data Model — Code Architecture Analyzer

> This system analyzes uploaded codebases and generates architecture diagrams
> and data flow visualizations.

## 1. Entities

### Entity: CodebaseProject

- **Description:** A codebase upload submitted by a user. Stores metadata about the uploaded zip file and tracks its analysis status.
- **Attributes:**

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| id | UUID | Yes | Unique identifier (primary key) |
| project_name | String | Yes | User-provided name for the project |
| upload_timestamp | Timestamp | Yes | When the zip was uploaded |
| zip_filename | String | Yes | Original filename of the uploaded zip |
| file_size_bytes | Integer | Yes | Size of the uploaded zip in bytes |
| status | Enum | Yes | one_of: pending, analyzing, complete, failed |
| error_message | String | No | Error details if status = failed |
| extract_path | String | Yes | Server-side path where zip was extracted |

### Entity: ArchitectureDiagram

- **Description:** Generated architecture diagram (mermaid/PlantUML) showing code components and dependencies.
- **Attributes:**

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| id | UUID | Yes | Unique identifier (primary key) |
| project_id | UUID | Yes | Foreign key to CodebaseProject |
| diagram_type | String | Yes | one_of: component, class, dependency |
| diagram_format | String | Yes | one_of: mermaid, plantuml, svg |
| diagram_content | Text | Yes | Raw diagram markup or SVG |
| generated_timestamp | Timestamp | Yes | When the diagram was generated |
| file_count | Integer | Yes | Number of files analyzed in this diagram |
| component_count | Integer | Yes | Number of components/modules identified |

### Entity: DataFlow

- **Description:** Represents a data flow path in the codebase (e.g., request → service → database).
- **Attributes:**

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| id | UUID | Yes | Unique identifier (primary key) |
| project_id | UUID | Yes | Foreign key to CodebaseProject |
| flow_name | String | Yes | Human-readable name (e.g., "User Registration Flow") |
| start_component | String | Yes | Entry point (e.g., API endpoint, UI handler) |
| end_component | String | Yes | Final destination (e.g., database, external service) |
| steps | Array<String> | Yes | Ordered list of intermediate components |
| description | Text | No | Human-readable description of the flow |

### Entity: CodeFile

- **Description:** Metadata about individual source files discovered during analysis.
- **Attributes:**

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| id | UUID | Yes | Unique identifier (primary key) |
| project_id | UUID | Yes | Foreign key to CodebaseProject |
| file_path | String | Yes | Relative path within the codebase |
| file_type | String | Yes | Language/extension (e.g., .ts, .py, .jsx) |
| imports | Array<String> | Yes | List of other files this file imports |
| exported_items | Array<String> | Yes | Functions, classes, or modules exported |
| line_count | Integer | Yes | Total lines of source code |

## 2. Relationships

| From | To | Type | Description |
|------|----|------|-------------|
| ArchitectureDiagram | CodebaseProject | N:1 | One project can have multiple diagram types (component, class, dependency) |
| DataFlow | CodebaseProject | N:1 | One project can have multiple data flows |
| CodeFile | CodebaseProject | N:1 | One project contains many source files |

## 3. Constraints

- Each CodebaseProject must have a unique project_name (per user session or user ID if multi-user later).
- CodebaseProject.status transitions are: pending → analyzing → complete (or failed at any step).
- ArchitectureDiagram.diagram_format must be one of the supported formats (mermaid, plantuml, svg).
- DataFlow.steps array must contain at least one intermediate component or be empty (for direct flows).
- CodeFile.file_path must be unique within a project.
- CodeFile.line_count must be ≥ 0.
- All timestamps use ISO 8601 UTC format.

## 4. Visualization

> A visual ER diagram showing CodebaseProject as the central hub, with
> ArchitectureDiagram, DataFlow, and CodeFile as dependent entities will
> be added once analysis tooling is finalized.
