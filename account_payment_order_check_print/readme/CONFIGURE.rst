Create a payment mode linked to the payment method **Check Payment Order** created by this module.

The information to print on the check (amount, payee, date, city, etc.) is positionned with a millimeter precision. The default position can be modified via an inherit of the method **_check_print_data()** from *account.payment*.

Some configuration parameters for the information to print on the check can be modified via an inherit of the method **_check_print_params()** from *account.payment*.
