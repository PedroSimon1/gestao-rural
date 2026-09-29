from django import forms


class LoginDemoForm(forms.Form):
    login = forms.CharField(
        max_length=150,
        error_messages={"required": "Informe o login."},
    )
    senha = forms.CharField(
        max_length=256,
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": "Informe a senha."},
    )
