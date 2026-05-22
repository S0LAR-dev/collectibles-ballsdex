from django.db import models
from django.core.exceptions import ValidationError

class GroupName(models.Model):
    group_name = models.CharField(
        max_length=20,
        default="collectible",
    )

    plural = models.CharField(
        max_length=21,
        default="collectibles",
    )

    def clean(self):
        if not self.pk and GroupName.objects.exists():
            raise ValidationError("Only one GroupName can be created.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        db_table = "groupname"
        verbose_name = "Group Name"
        verbose_name_plural = "Group Name"

    def __str__(self):
        return self.group_name

class Collectible(models.Model):
    REQUIREMENT_TYPES = [
        ("total", "Total Balls Owned"),
        ("shiny", "Shiny Balls Owned"),
        ("ball", "Specific Ball (1 required)"),
        ("balls", "Specific Ball (X required)"),
        ("special", "Special Card Ball"),
    ]

    requirement_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=REQUIREMENT_TYPES
    )

    requirement_value = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    name = models.CharField(max_length=50, unique=True)
    emoji = models.CharField(max_length=100)
    cost = models.IntegerField()
    bio = models.TextField(blank=True, null=True)
    image_url = models.CharField(max_length=300, blank=True, null=True)

    def __str__(self):
        return f"{self.emoji} {self.name}"
    
    class Meta:
        db_table = "collectible"
        verbose_name = "Collectible"
        verbose_name_plural = "Collectibles"

class PlayerCollectible(models.Model):
    player = models.ForeignKey("bd_models.Player", on_delete=models.CASCADE, related_name="collectibles")
    collectible = models.ForeignKey("Collectible", on_delete=models.CASCADE, related_name="owners")
    obtained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "playercollectible"
        unique_together = ("player", "collectible")
        indexes = [
            models.Index(fields=["player"]),
            models.Index(fields=["collectible"]),
        ]

    def __str__(self):
        return f"{self.player} owns {self.collectible}"
