# Platform: Joget DX

Documentation: https://dev.joget.org/community/
Version: (the version and edition your projects are built on, for example "Joget DX 9 Enterprise")
Confirmed by: –

What Joget DX gives as standard, what needs configuration, what needs custom work, and what it does not
support, feature by feature. `tools/platform_fit.py check` reads it to tell which parts of a project's spec
are more than the platform gives. **This starter sheet was written from general knowledge and none of it
has been checked yet**: each row is checked against the product's own documentation the first time a
project uses it (the Source and Checked columns), and confirmed by your lead developer (Confirmed).

- **Support:** `standard` (works as delivered), `configuration` (set up with the product's own tools),
  `custom` (needs code: a plugin, a script, custom HTML), `not supported`.
- **Spec:** the parts of a project spec the row covers, as `tools/platform_fit.py check` names them
  (`screen:form`, `field:signature`, `stat:formula`, `integration:*sap*` …). `*` matches anything; the
  first row that matches a feature is the one used, so specific rows come before general ones.
- **Block:** the building block in `building-blocks.md` that the work is estimated with.

| ID | Feature | Spec | Support | What it takes | Block | Source | Checked | Confirmed |
|---|---|---|---|---|---|---|---|---|
| PF-01 | Login page | screen:login | standard | The app's login page in the chosen theme | – | – | – | – |
| PF-02 | Data entry form | screen:form, field:text, field:textarea, field:select, field:radio, field:checkbox, field:number | standard | Form Builder elements and validators | BB-01 | – | – | – |
| PF-03 | Form in several steps | form:multi-page | standard | A multi-page form element | BB-02 | – | – | – |
| PF-04 | Date and date-time fields | field:date, field:datetime | standard | Date picker, with time when needed; rules between two dates are a validator or a script | BB-01 | – | – | – |
| PF-05 | File upload | field:file | standard | File upload element; size and type limits are settings | BB-01 | – | – | – |
| PF-06 | Choices from master data | field:lookup | standard | An options binder reading another form's data | BB-15 | – | – | – |
| PF-07 | Choosing a user | field:user | configuration | A select or popup bound to the directory's users | BB-01 | – | – | – |
| PF-08 | Signature | field:signature | configuration | A signature element (check the edition); placing it in a generated PDF is custom | BB-04 | – | – | – |
| PF-09 | Read-only view of a record | screen:detail | standard | The form shown read-only, or a view of the record | – | – | – | – |
| PF-10 | List of records | screen:list, list | standard | Datalist Builder: columns from a form's data | BB-06 | – | – | – |
| PF-11 | Filters, search and sorting on a list | list:filters, list:search, list:sort | standard | Datalist filters and sorting | BB-06 | – | – | – |
| PF-12 | Actions on a row | list:row actions | standard | Datalist row actions and links | BB-06 | – | – | – |
| PF-13 | Actions shown only for some statuses or roles | list:conditional actions, list:actions by role | configuration | Visibility rules or permissions on each action | BB-06 | – | – | – |
| PF-14 | Task list of what waits for the signed-in user | list:task inbox | standard | The inbox of workflow assignments | BB-03 | – | – | – |
| PF-15 | A list that shows each role different records | list:filter by role, role:data scope | configuration | Datalist filters on the current user or group, or one list per role | BB-14 | – | – | – |
| PF-16 | Dashboard with counts per status | screen:dashboard, stat:count | configuration | Counts in a dashboard or menu page; counts that open a filtered list when clicked are custom | BB-07 | – | – | – |
| PF-17 | Figures with a calculation of their own | stat:formula | custom | Calculated in a script, an SQL query or a plugin | BB-08 | – | – | – |
| PF-18 | Approval workflow, statuses and decisions | workflow, dialog | standard | Process Builder: activities, participants, routes, reject paths, a form for each decision | BB-03 | – | – | – |
| PF-19 | Approval history shown on the record | approval progress | custom | The history is kept by the workflow; showing it on the form needs a list built on that data | BB-17 | – | – | – |
| PF-20 | Roles and their menus | role | standard | Permissions on menus and groups of users | BB-14 | – | – | – |
| PF-21 | E-mail when something happens | notification:email | standard | An e-mail tool on the workflow step | BB-12 | – | – | – |
| PF-22 | Reminders and escalations | notification:reminder | configuration | Deadlines on workflow steps, or a scheduler (check the edition) | BB-11 | – | – | – |
| PF-23 | Export to Excel | action:*export*, action:*excel* | standard | Datalist export | BB-13 | – | – | – |
| PF-24 | Generated PDF | action:*pdf*, action:*print* | configuration | A form exported to PDF; a document with its own layout is custom | BB-10 | – | – | – |
| PF-25 | Starting a record from an earlier one | action:*copy* | custom | Filling a new form from another record needs a custom load binder or script | BB-01 | – | – | – |
| PF-26 | Other buttons and actions | action:* | standard | Form buttons, menu links and workflow actions | – | – | – | – |
| PF-27 | Sign-in with the company directory (AD, LDAP, SSO) | integration:*active directory*, integration:*ldap*, integration:*sso*, integration:*entra*, integration:*azure ad* | configuration | A directory manager and single sign-on plugins (check the edition) | BB-16 | – | – | – |
| PF-28 | Sending e-mail through the company's mail server | integration:*smtp*, integration:*mail* | standard | The platform's e-mail settings | – | – | – | – |
| PF-29 | Exchange with another system | integration:* | custom | An API tool or a plugin, per endpoint, with its error handling | BB-09 | – | – | – |
| PF-30 | Look, branding and text size | look:theme, look:text size | configuration | Theme settings and custom CSS | – | – | – | – |
| PF-31 | A screen of its own design | screen:custom | custom | Custom HTML or a plugin | – | – | – | – |
| PF-32 | What the mock-up does beyond the spec | code:project | custom | The project's own mock-up code shows behaviour the spec cannot describe: each piece needs building on the platform | – | – | – | – |
| PF-33 | Managing users, groups and roles from the app's own screens | screen:user management | custom | Users and groups live in the platform's directory (its own, or the company directory through a directory manager) and are managed in the admin console; screens in the app that add or change them need forms or a plugin bound to the directory (check the edition) | BB-15 | – | – | – |
