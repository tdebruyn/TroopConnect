def is_animateur(request):
    if request.user.is_authenticated and hasattr(request.user, "person"):
        try:
            person = request.user.person
            is_anim = person.primary_role.short in ["a", "ar"]
            # Staff or users with secondary role 'ar' or 'ad' can send to all
            has_send_all_role = request.user.is_staff or person.roles.filter(short__in=["ar", "ad"]).exists()
            is_tresorier = person.roles.filter(short="t").exists()
            return {
                "user_is_animateur": is_anim,
                "user_can_send_all": has_send_all_role,
                "user_is_tresorier": is_tresorier or request.user.is_staff,
            }
        except Exception:
            pass
    return {"user_is_animateur": False, "user_can_send_all": False, "user_is_tresorier": False}
