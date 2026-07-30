from app.services.image_storage import ImageStorage


storage = ImageStorage()

file_path = storage.create_file_path("jpg")

print(file_path)