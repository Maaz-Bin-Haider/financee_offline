from django.db import models

# No models. Like every other business app here, the draft invoice's state lives
# in each tenant schema -- draftinvoices, draftitems, draftunits and draftreturns,
# created by tenancy/sql/add_draft_invoices.sql -- and is reached only through
# stored procedures.
