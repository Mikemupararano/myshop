from cart.cart import Cart
from django.shortcuts import redirect, render
from .forms import OrderCreateForm
from .models import OrderItem
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


# from cart.cart import Cart
# from django.shortcuts import render
# from .forms import OrderCreateForm
# from .models import OrderItem

# # Create your views here.
# def order_create(request):
#     cart = Cart(request)
#     if request.method == "POST":
#         form = OrderCreateForm(request.POST)
#         if form.is_valid():
#             order = form.save()
#             for item in cart:
#                 OrderItem.objects.create(
#                     order=order,
#                     product=item["product"],
#                     price=item["price"],
#                     quantity=item["quantity"],
#                 )
#                 # clear the cart
#             cart.clear()
#             return render(
#                 request,
#                 "orders/order/created.html",
#                 {"order": order},
#             )
#     else:
#         form = OrderCreateForm()
#     return render(
#         request,
#         "orders/order/create.html",
#         {"cart": cart, "form": form},
#     )
