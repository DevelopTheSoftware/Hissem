from django.db import models
from django.contrib.auth.models import User

class Portfolio(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    stock_code = models.CharField(max_length=10)
    buy_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    buy_date = models.DateField()

    def __str__(self):
        return f"{self.user.username} - {self.stock_code}"
