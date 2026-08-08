insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('private-media', 'private-media', false, 10000000, array['image/jpeg','image/png','image/heic','image/webp'])
on conflict (id) do update set public = false;

create policy "Owners can read private media" on storage.objects for select to authenticated
using (bucket_id = 'private-media' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "Owners can upload private media" on storage.objects for insert to authenticated
with check (bucket_id = 'private-media' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "Owners can delete private media" on storage.objects for delete to authenticated
using (bucket_id = 'private-media' and (storage.foldername(name))[1] = auth.uid()::text);
