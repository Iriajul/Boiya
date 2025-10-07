from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from django.forms import TextInput, Textarea
from django import forms

# Optional: custom forms for admin
class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = '__all__'
        widgets = {
            'username': TextInput(attrs={'size': 20}),
            'full_name': TextInput(attrs={'size': 30}),
        }

class UserAdmin(BaseUserAdmin):
    form = UserAdminForm
    model = User

    list_display = ('email', 'username', 'full_name', 'is_staff', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'username', 'full_name')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'username', 'full_name', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_superuser', 'is_active', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'full_name', 'password1', 'password2', 'is_staff', 'is_superuser', 'is_active')}
        ),
    )

admin.site.register(User, UserAdmin)
