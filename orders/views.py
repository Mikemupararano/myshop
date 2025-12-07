from django.contrib.admin.views.decorators import staff_member_required
from cart.cart import Cart
from django.shortcuts import get_object_or_404, redirect, render
from .forms import OrderCreateForm
from .models import Order, OrderItem
from .tasks import order_created


def order_create(request):
    cart = Cart(request)

    if request.method == "POST":
        form = OrderCreateForm(request.POST)

        if form.is_valid():
            # Save the order
            order = form.save()

            # Create corresponding OrderItem objects
            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    price=item["price"],
                    quantity=item["quantity"],
                )

            # Clear the cart AFTER saving order items
            cart.clear()
            # Launch asynchronous task to send order confirmation email
            order_created.delay(order.id)
            # set the order in the session
            request.session["order_id"] = order.id
            # Redirect to the payment processing
            return redirect("payment:process")

            # Optional: Redirect to prevent duplicate POSTs (good practice)
            # return render(request, "orders/order/created.html", {"order": order})

    else:
        form = OrderCreateForm()

    return render(
        request,
        "orders/order/create.html",
        {"cart": cart, "form": form},
    )


@staff_member_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(
        request,
        "admin/orders/order/detail.html",
        {"order": order},
    )
