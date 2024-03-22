"""SCB Credit .csv importer."""

from beancount_reds_importers.libreader import xlsreader
from beancount_reds_importers.libtransactionbuilder import banking
import re
from beancount.core.number import D


class Importer(xlsreader.Importer, banking.Importer):
    IMPORTER_NAME = "SCB Card CSV"

    def custom_init(self):
        self.max_rounding_error = 0.04
        self.filename_pattern_def = "^CC_TXN_History[0-9]*"
        self.header_identifier = self.config.get(
            "custom_header", "United Overseas Bank Limited.*Account Type:VISA SIGNATURE"
        )
        self.column_labels_line = "Transaction Date,Posting Date,Description,Foreign Currency Type,Transaction Amount(Foreign),Local Currency Type,Transaction Amount(Local)"  # noqa: E501
        self.date_format = "%d %b %Y"

        # Remove _DISABLED below to include currency conversions. This won't work as expected since
        # Beancount v2 doesn't support adding @@ (total price conversions) via code. See
        # https://groups.google.com/g/beancount/c/nMvuoR4yOmM This means the '@' generated by this
        # code below needs to be replaced with an '@@'

        foreign_currency = "foreign_currency_DISABLED"
        foreign_amount = "foreign_amount_DISABLED"
        if self.config.get("convert_currencies", False):
            foreign_currency = "foreign_currency"
            foreign_amount = "foreign_amount"

        # fmt: off
        self.header_map = {
            "Transaction Date":             "date",
            "Posting Date":                 "date_posting",
            "Description":                  "payee",
            "Foreign Currency Type":        foreign_currency,
            "Transaction Amount(Foreign)":  foreign_amount,
            "Local Currency Type":          "currency",
            "Transaction Amount(Local)":    "amount",
        }
        # fmt: on
        self.transaction_type_map = {}
        self.skip_transaction_types = []

    def deep_identify(self, file):
        account_number = self.config.get("account_number", "")
        return (
            re.match(self.header_identifier, file.head())
            and account_number in file.head()
        )

    # TODO: move into utils, since this is probably a common operation
    def prepare_table(self, rdr):
        # Remove carriage returns in description
        rdr = rdr.convert("Description", lambda x: x.replace("\n", " "))
        rdr = rdr.addfield("memo", lambda x: "")

        # delete empty rows
        rdr = rdr.select(lambda x: x["Transaction Date"] != "")
        return rdr

    def prepare_processed_table(self, rdr):
        return rdr.convert("amount", lambda x: -1 * D(str(x)))

    def prepare_raw_file(self, rdr):
        # Strip tabs and spaces around each field in the entire file
        rdr = rdr.convertall(lambda x: x.strip(" \t") if isinstance(x, str) else x)

        # Delete empty rows
        rdr = rdr.select(lambda x: any([i != "" for i in x]))

        return rdr

    def get_balance_statement(self, file=None):
        """Return the balance on the first and last dates"""
        date = self.get_balance_assertion_date()
        if date:
            balance_row = self.get_row_by_label(file, "Statement Balance:")
            units, currency = balance_row[1], balance_row[2]
            yield banking.Balance(date, -1 * D(str(units)), currency)
