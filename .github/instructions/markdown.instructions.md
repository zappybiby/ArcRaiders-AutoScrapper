---

applyTo: "**/*.md"

# Markdown Content Standards

<Standards>

**Structure**:

- Use `##` for H2, `###` for H3; avoid H4+ (restructure instead)
- No H1 headings (generated from title/frontmatter)
- Use `-` for bullets, `1.` for numbered lists, 2-space indent for nesting

**Code Blocks**: Triple backticks with language specifier for syntax highlighting

**Links**: `[descriptive text](URL)` - ensure valid and accessible

**Images**: `![alt text](URL)` - always include alt text

**Tables**: `|` with aligned columns and headers

**Formatting**:

- Line length: soft-wrap at 80 chars, hard limit at 400
- Blank lines between sections
- YAML frontmatter with required metadata

</Standards>

<WhatToAdd>

When creating markdown content, include:

- Frontmatter with relevant metadata fields
- Descriptive headings in hierarchical order
- Code blocks with language tags
- Alt text on all images
- Valid internal and external links

</WhatToAdd>

<Limitations>

- No H1 headings in content body
- No excessive whitespace
- No broken or placeholder links
- No images without alt text
- No code blocks without language specifier

</Limitations>
