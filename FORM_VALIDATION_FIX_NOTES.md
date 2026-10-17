# Form validation fixes (beta.3 candidate)

- Insurance, tax and financing: preserve entered values when saving fails.
- Insurance and tax: show field-specific date errors and map known backend validation errors to the affected fields.
- Financing: preserve values and report identifiable start-date/duration errors.
- Maintenance, toll/vignette and other expenses: existing field-specific validation and value retention remain unchanged.
- No database migration or currency conversion.

## Test before release

For all six forms, test an invalid date/amount and verify values remain; then correct and save. Verify edits preserve existing records. Test insurance dates and premium, tax dates and amount, leasing duration/start date, and all expense groups. Full HA UI testing has not been performed.
