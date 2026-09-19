# Merged Rulebook

## Shared Implementation Guidance

- Store the source clause, page number and extraction confidence for each finding.
- Do not infer compliance when a required document or fact is missing.
- Use current official legislation and government guidance for validation.
- Keep legal rules versioned and record their effective dates.
- Separate factual extraction, rule triggering and human legal review.
- Use official tax and planning services where calculations or property-level data are required.

### VIC-CON-001
- jurisdiction: VIC
- category: contract
- source: Victoria Residential Contract Rulebook
- check: Contract date, parties and property address
- suggested_output: Verify required fields

### VIC-CON-002
- jurisdiction: VIC
- category: contract
- source: Victoria Residential Contract Rulebook
- check: Purchase price and deposit extracted
- suggested_output: Check consistency

### VIC-CON-003
- jurisdiction: VIC
- category: contract
- source: Victoria Residential Contract Rulebook
- check: Finance condition and deadline
- suggested_output: Track approval deadline

### VIC-CON-004
- jurisdiction: VIC
- category: contract
- source: Victoria Residential Contract Rulebook
- check: Settlement date and time
- suggested_output: Verify settlement terms

### VIC-DISC-001
- jurisdiction: VIC
- category: disclosure
- source: Victoria Residential Contract Rulebook
- check: Section 32 statement evidence
- suggested_output: Flag missing or incomplete disclosure

### VIC-DISC-002
- jurisdiction: VIC
- category: disclosure
- source: Victoria Residential Contract Rulebook
- check: Title, easements, covenants and mortgages
- suggested_output: Request title review

### VIC-SET-001
- jurisdiction: VIC
- category: contract
- source: Victoria Residential Contract Rulebook
- check: Default, termination and interest clauses
- suggested_output: Professional legal review

### VIC-SET-002
- jurisdiction: VIC
- category: contract
- source: Victoria Residential Contract Rulebook
- check: Settlement extension provisions
- suggested_output: Verify notice and consent

### NSW-CON-001
- jurisdiction: NSW
- category: contract
- source: NSW Residential Contract Rulebook
- check: Contract parties, property and price
- suggested_output: Verify required fields

### NSW-DISC-001
- jurisdiction: NSW
- category: disclosure
- source: NSW Residential Contract Rulebook
- check: Prescribed contract attachments
- suggested_output: Flag missing documents

### NSW-DISC-002
- jurisdiction: NSW
- category: disclosure
- source: NSW Residential Contract Rulebook
- check: Title, deposited plan and certificates
- suggested_output: Request document verification

### NSW-COOL-001
- jurisdiction: NSW
- category: contract
- source: NSW Residential Contract Rulebook
- check: Cooling-off statement and exceptions
- suggested_output: Flag for legal review

### NSW-DEP-001
- jurisdiction: NSW
- category: contract
- source: NSW Residential Contract Rulebook
- check: Deposit amount and holding arrangements
- suggested_output: Verify contract terms

### NSW-SET-001
- jurisdiction: NSW
- category: contract
- source: NSW Residential Contract Rulebook
- check: Settlement date and completion conditions
- suggested_output: Track deadline

### NSW-DEF-001
- jurisdiction: NSW
- category: contract
- source: NSW Residential Contract Rulebook
- check: Default, rescission and termination terms
- suggested_output: Professional legal review

### PLAN-001
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Property zoning identified
- suggested_output: Verify permitted land uses

### PLAN-002
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Heritage overlay or heritage listing
- suggested_output: Check permit requirements

### PLAN-003
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Flood or bushfire constraint
- suggested_output: Request hazard verification

### PLAN-004
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Tree protection or vegetation controls
- suggested_output: Flag development restrictions

### PLAN-005
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Right of way or access restriction
- suggested_output: Review title and access

### PLAN-006
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Utility, drainage or sewer easement
- suggested_output: Check building limitations

### PLAN-007
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Planning certificate or report missing
- suggested_output: Missing evidence

### PLAN-008
- jurisdiction: AU-wide
- category: planning
- source: Australian Planning & Property Restrictions Rulebook
- check: Covenant or restrictive condition
- suggested_output: Legal and planning review

### TAX-001
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: GST included, excluded or unclear
- suggested_output: Verify GST treatment

### TAX-002
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: Vendor GST registration statement
- suggested_output: Request tax verification

### TAX-003
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: Transfer duty exposure
- suggested_output: Use official state calculator

### TAX-004
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: Foreign purchaser or absentee-owner issue
- suggested_output: Check applicable rules

### TAX-005
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: Land tax responsibility or adjustment
- suggested_output: Review contract allocation

### TAX-006
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: Tax clause inconsistency
- suggested_output: Flag for professional advice

### TAX-007
- jurisdiction: AU-wide
- category: tax
- source: Australian Property Tax & GST Rulebook
- check: Missing purchaser status information
- suggested_output: Return information required

### STRATA-001
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Strata or owners corporation identified
- suggested_output: Request records

### STRATA-002
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Outstanding or special levies
- suggested_output: Financial review

### STRATA-003
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: By-laws and use restrictions
- suggested_output: Review purchaser obligations

### STRATA-004
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Building defects or ongoing litigation
- suggested_output: Request documents

### PROP-001
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Building and pest report status
- suggested_output: Flag missing inspection

### PROP-002
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Repair obligation before settlement
- suggested_output: Track completion evidence

### PROP-003
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Insurance coverage or transfer language
- suggested_output: Verify coverage

### PROP-004
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Septic, drainage or utility condition
- suggested_output: Request technical verification

### PROP-005
- jurisdiction: AU-wide
- category: strata
- source: Strata, Owners Corporation & Property Condition Rulebook
- check: Fixtures and chattels exclusions
- suggested_output: Compare contract inventory
