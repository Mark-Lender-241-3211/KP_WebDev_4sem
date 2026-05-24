def user_roles(request):
    user = request.user

    is_librarian = (
        user.is_authenticated
        and user.groups.filter(name='Библиотекарь').exists()
    )

    is_admin = (
        user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(name='Администратор').exists()
        )
    )

    return {
        'is_librarian_user': is_librarian,
        'is_admin_user': is_admin,
    }