Transfer all backend and hardware integration work from `experimental-hardware-merge` to `main`, ensuring everything works and is demoable, while excluding website/frontend changes and security components.

Integrity mode: [OPEN: Which shortcuts should the team NOT be allowed to take?]

## Requirements

### R1. Hardware and Backend Transfer to Main
Transfer all backend and hardware integration work from branch `experimental-hardware-merge` to `main`, including firmware, hardware gateway, backend hardware endpoints, serial bridge, and tests.
[OPEN: Scope of hardware developer tools, skills, and documentation to include in transfer]

### R2. Frontend / Website Exclusion
Do not transfer website or frontend changes from `experimental-hardware-merge`; keep `main`'s existing website.

### R3. Security Exclusion
Exclude all security components from the transfer, specifically the Winstead cyber incident response and air-gap killswitch UI and backend routes.

### R4. System Functionality and Demo Readiness
Ensure everything works and is demoable, all relevant tests pass, and the system runs cleanly on `main`.
[OPEN: Verification environment and test suites to execute]

## Acceptance Criteria

### Branch and Scope
- [ ] Current git branch is `main`.
- [ ] Backend and hardware integration files (firmware, hardware gateway, backend hardware endpoints, serial bridge) from `experimental-hardware-merge` are present on `main`.
- [ ] Website and frontend files on `main` are preserved without website changes from `experimental-hardware-merge`.
- [ ] Winstead cyber incident response files, routes, and killswitch components are excluded from `main`.

### Verification and Clean Operation
- [ ] [OPEN: Acceptance criteria for test suites and demo verification]
