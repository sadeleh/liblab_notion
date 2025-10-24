"""
Cloud-agnostic storage service layer for file management.
Follows clean architecture principles with abstract interface and concrete implementations.
"""
from abc import ABC, abstractmethod
from typing import BinaryIO, Optional
import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)


class StorageService(ABC):
    """Abstract interface for storage operations."""
    
    @abstractmethod
    def upload_file(self, file_obj: BinaryIO, filename: str, content_type: Optional[str] = None) -> dict:
        """
        Upload a file to storage.
        
        Args:
            file_obj: File object to upload
            filename: Name for the stored file
            content_type: MIME type of the file
            
        Returns:
            dict with 'success', 'url', 'filename', 'size' keys
        """
        pass
    
    @abstractmethod
    def get_file_url(self, filename: str) -> str:
        """
        Get the URL to access a file.
        
        Args:
            filename: Name of the file
            
        Returns:
            URL string
        """
        pass
    
    @abstractmethod
    def delete_file(self, filename: str) -> bool:
        """
        Delete a file from storage.
        
        Args:
            filename: Name of the file to delete
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def file_exists(self, filename: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            filename: Name of the file
            
        Returns:
            True if file exists, False otherwise
        """
        pass
    
    @abstractmethod
    def get_file_size(self, filename: str) -> Optional[int]:
        """
        Get the size of a file in bytes.
        
        Args:
            filename: Name of the file
            
        Returns:
            File size in bytes or None if file doesn't exist
        """
        pass


class S3StorageService(StorageService):
    """AWS S3 implementation of storage service.
    
    Uses presigned URLs for secure access to private S3 buckets.
    Files are kept private and URLs expire after 1 hour.
    """
    
    def __init__(self, bucket_name: str, region: str = 'eu-central-1', folder: str = 'ws-general/recordings', workspace_id: str = 'ws-general'):
        """
        Initialize S3 storage service.
        
        Args:
            bucket_name: S3 bucket name
            region: AWS region (default: eu-central-1)
            folder: Folder prefix in the bucket (default: ws-general/recordings) - deprecated, use workspace_id
            workspace_id: Workspace ID for multi-tenancy (default: ws-general)
        """
        self.bucket_name = bucket_name
        self.region = region
        self.workspace_id = workspace_id
        # Use workspace_id to construct folder path
        self.folder = f"{workspace_id}/recordings/"
        
        # Initialize S3 client with credentials from environment
        try:
            from botocore.config import Config
            
            # Use signature version 4 and region-specific endpoint
            config = Config(
                region_name=self.region,
                signature_version='s3v4',
                s3={'addressing_style': 'virtual'}
            )
            
            self.s3_client = boto3.client(
                's3',
                region_name=self.region,
                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
                config=config
            )
            logger.info(f"Initialized S3 storage: bucket={bucket_name}, region={region}, workspace={workspace_id}")
        except NoCredentialsError:
            logger.error("AWS credentials not found in environment variables")
            raise ValueError("AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.")
    
    def _get_s3_key(self, filename: str) -> str:
        """Get the full S3 key (path) for a filename."""
        return f"{self.folder}{filename}"
    
    def upload_file(self, file_obj: BinaryIO, filename: str, content_type: Optional[str] = None) -> dict:
        """Upload a file to S3."""
        try:
            # Secure the filename
            secure_name = secure_filename(filename)
            s3_key = self._get_s3_key(secure_name)
            
            # Get file size first (before upload)
            file_obj.seek(0, os.SEEK_END)
            file_size = file_obj.tell()
            file_obj.seek(0)  # Reset to beginning
            
            # Prepare upload arguments
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Note: Public access is controlled by bucket policy, not ACLs
            # Do not set ACL as bucket has ACLs disabled
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            
            # Generate URL
            url = self.get_file_url(secure_name)
            
            logger.info(f"Successfully uploaded file to S3: {s3_key} ({file_size} bytes)")
            
            return {
                'success': True,
                'url': url,
                'filename': secure_name,
                'size': file_size
            }
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"S3 upload failed: {error_code} - {str(e)}")
            return {
                'success': False,
                'error': f"S3 upload failed: {error_code}",
                'filename': filename
            }
        except Exception as e:
            logger.error(f"Unexpected error during S3 upload: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'filename': filename
            }
    
    def get_file_url(self, filename: str) -> str:
        """Get presigned URL for a file in S3."""
        s3_key = self._get_s3_key(filename)
        # For private buckets, generate a presigned URL (valid for 1 hour)
        try:
            # IMPORTANT: Use region-specific endpoint to avoid 307 redirects
            # which invalidate the presigned signature
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key
                },
                ExpiresIn=3600  # URL valid for 1 hour
            )
            
            # Replace generic s3.amazonaws.com with region-specific endpoint
            # This prevents 307 redirects that break the signature
            if '.s3.amazonaws.com/' in presigned_url:
                presigned_url = presigned_url.replace(
                    '.s3.amazonaws.com/',
                    f'.s3.{self.region}.amazonaws.com/'
                )
            
            return presigned_url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            # Fallback to direct URL (will fail if bucket is private, but better than crashing)
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
    
    def delete_file(self, filename: str) -> bool:
        """Delete a file from S3."""
        try:
            s3_key = self._get_s3_key(filename)
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            logger.info(f"Successfully deleted file from S3: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 delete: {str(e)}")
            return False
    
    def file_exists(self, filename: str) -> bool:
        """Check if a file exists in S3."""
        try:
            s3_key = self._get_s3_key(filename)
            self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return True
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == '404':
                return False
            logger.error(f"Error checking file existence: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking file existence: {str(e)}")
            return False
    
    def get_file_size(self, filename: str) -> Optional[int]:
        """Get the size of a file in S3."""
        try:
            s3_key = self._get_s3_key(filename)
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return response.get('ContentLength')
        except ClientError:
            return None
        except Exception as e:
            logger.error(f"Error getting file size: {str(e)}")
            return None
    
    def download_file(self, filename: str, destination_path: str) -> bool:
        """
        Download a file from S3 to local filesystem.
        
        Args:
            filename: Name of the file in S3
            destination_path: Local path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            s3_key = self._get_s3_key(filename)
            self.s3_client.download_file(
                self.bucket_name,
                s3_key,
                destination_path
            )
            logger.info(f"Successfully downloaded file from S3: {s3_key} -> {destination_path}")
            return True
        except ClientError as e:
            logger.error(f"S3 download failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 download: {str(e)}")
            return False
    
    def upload_from_path(self, local_path: str, filename: str, content_type: Optional[str] = None) -> dict:
        """
        Upload a file from local filesystem to S3.
        
        Args:
            local_path: Path to the local file
            filename: Name for the file in S3
            content_type: MIME type of the file
            
        Returns:
            dict with 'success', 'url', 'filename', 'size' keys
        """
        try:
            # Get file size first (before opening)
            file_size = os.path.getsize(local_path)
            
            # Open and upload
            with open(local_path, 'rb') as file_obj:
                # Secure the filename
                secure_name = secure_filename(filename)
                s3_key = self._get_s3_key(secure_name)
                
                # Prepare upload arguments
                extra_args = {}
                if content_type:
                    extra_args['ContentType'] = content_type
                
                # Upload to S3
                self.s3_client.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs=extra_args
                )
                
                # Generate URL
                url = self.get_file_url(secure_name)
                
                logger.info(f"Successfully uploaded file to S3: {s3_key} ({file_size} bytes)")
                
                return {
                    'success': True,
                    'url': url,
                    'filename': secure_name,
                    'size': file_size
                }
                
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.error(f"S3 upload failed: {error_code} - {str(e)}")
            return {
                'success': False,
                'error': f"S3 upload failed: {error_code}",
                'filename': filename
            }
        except Exception as e:
            logger.error(f"Error uploading from path: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'filename': filename
            }


class LocalStorageService(StorageService):
    """Local filesystem implementation of storage service (for testing/fallback)."""
    
    def __init__(self, base_path: str, base_url: str = '/voice_recordings'):
        """
        Initialize local storage service.
        
        Args:
            base_path: Base directory path for storing files
            base_url: Base URL path for serving files
        """
        self.base_path = base_path
        self.base_url = base_url.rstrip('/')
        
        # Create directory if it doesn't exist
        os.makedirs(self.base_path, exist_ok=True)
        logger.info(f"Initialized local storage: path={base_path}")
    
    def _get_file_path(self, filename: str) -> str:
        """Get the full filesystem path for a filename."""
        return os.path.join(self.base_path, filename)
    
    def upload_file(self, file_obj: BinaryIO, filename: str, content_type: Optional[str] = None) -> dict:
        """Upload a file to local filesystem."""
        try:
            secure_name = secure_filename(filename)
            file_path = self._get_file_path(secure_name)
            
            # Save file
            file_obj.seek(0)
            with open(file_path, 'wb') as f:
                f.write(file_obj.read())
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Generate URL
            url = self.get_file_url(secure_name)
            
            logger.info(f"Successfully uploaded file locally: {file_path} ({file_size} bytes)")
            
            return {
                'success': True,
                'url': url,
                'filename': secure_name,
                'size': file_size
            }
        except Exception as e:
            logger.error(f"Local upload failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'filename': filename
            }
    
    def get_file_url(self, filename: str) -> str:
        """Get the URL for serving a local file."""
        return f"{self.base_url}/{filename}"
    
    def delete_file(self, filename: str) -> bool:
        """Delete a file from local filesystem."""
        try:
            file_path = self._get_file_path(filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Successfully deleted local file: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Local delete failed: {str(e)}")
            return False
    
    def file_exists(self, filename: str) -> bool:
        """Check if a file exists in local filesystem."""
        file_path = self._get_file_path(filename)
        return os.path.exists(file_path)
    
    def get_file_size(self, filename: str) -> Optional[int]:
        """Get the size of a local file."""
        try:
            file_path = self._get_file_path(filename)
            if os.path.exists(file_path):
                return os.path.getsize(file_path)
            return None
        except Exception as e:
            logger.error(f"Error getting file size: {str(e)}")
            return None


def create_storage_service(use_s3: bool = True, workspace_id: str = 'ws-general') -> StorageService:
    """
    Factory function to create the appropriate storage service.
    
    Args:
        use_s3: If True, use S3 storage; otherwise use local storage
        workspace_id: Workspace ID for multi-tenancy (default: ws-general)
        
    Returns:
        StorageService instance
    """
    if use_s3:
        # Check if AWS credentials are available
        if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
            logger.warning("AWS credentials not found. Falling back to local storage.")
            use_s3 = False
    
    if use_s3:
        return S3StorageService(
            bucket_name='liblib-notion',
            region='eu-central-1',
            workspace_id=workspace_id
        )
    else:
        # Fallback to local storage
        from flask import current_app
        return LocalStorageService(
            base_path=current_app.config.get('UPLOAD_FOLDER', 'instance/voice_recordings'),
            base_url='/voice_recordings'
        )

