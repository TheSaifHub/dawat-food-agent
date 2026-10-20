-- ════════════════════════════════════════════════════════════════════════
-- 0006 · Where a cart is delivered   (D-025)
-- The delivery fee depends on the distance from each branch to the delivery point, and the chat and the
-- website share one cart, so the cart remembers it: an area, and optionally one of the user's addresses
-- (whose coordinates then give the distance; otherwise the area's centre does).
-- Guards (second layer; the cart tools check in code first):
--   · the address must belong to the cart's user and lie in the cart's delivery area
--   · a CONFIRMED cart's delivery point can't change: the total the user said "yes" to can't move
-- ════════════════════════════════════════════════════════════════════════

alter table public.carts
  add column if not exists delivery_area_id text references public.areas (area_id),
  add column if not exists address_id uuid references public.addresses (address_id) on delete set null;

create or replace function public.carts_delivery_guard() returns trigger
language plpgsql set search_path = '' as $$
declare
  a_user uuid; a_area text;
begin
  if tg_op = 'UPDATE' and old.status = 'confirmed' and new.status = 'confirmed'
     and (new.delivery_area_id is distinct from old.delivery_area_id or new.address_id is distinct from old.address_id) then
    raise exception 'cart % is confirmed; its delivery point can only change after it is re-opened', new.cart_id
      using errcode = 'check_violation';
  end if;
  if new.address_id is not null then
    select user_id, area_id into a_user, a_area from public.addresses where address_id = new.address_id;
    if a_user is distinct from new.user_id then
      raise exception 'address % does not belong to the owner of cart %', new.address_id, new.cart_id
        using errcode = 'check_violation';
    end if;
    if a_area is distinct from new.delivery_area_id then
      raise exception 'address % is in %, not in the cart''s delivery area %', new.address_id, a_area, new.delivery_area_id
        using errcode = 'check_violation';
    end if;
  end if;
  return new;
end $$;
create or replace trigger carts_delivery_guard
  before insert or update on public.carts for each row execute function public.carts_delivery_guard();

revoke execute on function public.carts_delivery_guard() from public, anon, authenticated;
